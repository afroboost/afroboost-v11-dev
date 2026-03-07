// OnboardingTunnel.js - Tunnel d'onboarding 3 étapes (Nom, WhatsApp, Email)
// Affiché AVANT le chat quand un visiteur arrive via un lien personnalisé /?link={token}
// v16.0 - Module Conversations & Tunnels de Chat Isolés

import React, { useState, useCallback } from 'react';

const STEPS = [
  { id: 1, label: 'Votre nom', field: 'name', type: 'text', placeholder: 'Ex: Marie Dupont', icon: '👤' },
  { id: 2, label: 'Votre WhatsApp', field: 'whatsapp', type: 'tel', placeholder: 'Ex: +41 79 123 45 67', icon: '📱' },
  { id: 3, label: 'Votre email', field: 'email', type: 'email', placeholder: 'Ex: marie@gmail.com', icon: '✉️' }
];

const OnboardingTunnel = ({ linkToken, onComplete, welcomeTitle }) => {
  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState({ name: '', whatsapp: '', email: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const API = (process.env.REACT_APP_BACKEND_URL || '') + '/api';

  const validateStep = useCallback((step, value) => {
    if (!value || !value.trim()) {
      return 'Ce champ est requis';
    }
    if (step === 2) {
      // Validation WhatsApp basique
      const cleaned = value.replace(/[\s\-().]/g, '');
      if (cleaned.length < 8) return 'Numéro trop court';
      if (!/^[+]?\d+$/.test(cleaned)) return 'Format invalide';
    }
    if (step === 3) {
      // Validation email basique
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())) return 'Email invalide';
    }
    return null;
  }, []);

  const handleNext = useCallback(async () => {
    const step = STEPS[currentStep - 1];
    const value = formData[step.field];
    const validationError = validateStep(currentStep, value);

    if (validationError) {
      setError(validationError);
      return;
    }

    setError('');

    if (currentStep < 3) {
      setCurrentStep(prev => prev + 1);
      return;
    }

    // Étape 3 complétée → appeler smart-entry
    setLoading(true);
    try {
      const response = await fetch(`${API}/chat/smart-entry`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formData.name.trim(),
          email: formData.email.trim(),
          whatsapp: formData.whatsapp.trim(),
          link_token: linkToken
        })
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Erreur serveur');
      }

      const data = await response.json();
      const participantId = data.participant?.id || data.participant_id;
      const sessionId = data.session?.id || data.session_id;

      // Sauvegarder dans localStorage pour ne pas redemander
      if (participantId) {
        localStorage.setItem(`af_participant_${linkToken}`, JSON.stringify({
          id: participantId,
          name: formData.name.trim(),
          email: formData.email.trim(),
          whatsapp: formData.whatsapp.trim(),
          sessionId: sessionId
        }));
      }

      onComplete(participantId, sessionId, {
        firstName: formData.name.trim(),
        email: formData.email.trim(),
        whatsapp: formData.whatsapp.trim()
      });
    } catch (err) {
      console.error('[ONBOARDING] Erreur smart-entry:', err);
      setError(err.message || 'Impossible de continuer. Réessayez.');
    } finally {
      setLoading(false);
    }
  }, [currentStep, formData, linkToken, onComplete, validateStep, API]);

  const handleBack = useCallback(() => {
    if (currentStep > 1) {
      setCurrentStep(prev => prev - 1);
      setError('');
    }
  }, [currentStep]);

  const handleKeyPress = useCallback((e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleNext();
    }
  }, [handleNext]);

  const step = STEPS[currentStep - 1];

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '32px 24px',
      minHeight: '400px',
      background: 'linear-gradient(180deg, #0a0a0a 0%, #1a0a1a 100%)',
      borderRadius: '16px',
      width: '100%',
      maxWidth: '420px',
      margin: '0 auto'
    }}>
      {/* Logo / Titre */}
      <div style={{ textAlign: 'center', marginBottom: '32px' }}>
        <div style={{
          fontSize: '36px',
          marginBottom: '8px'
        }}>💬</div>
        <h2 style={{
          color: '#ffffff',
          fontSize: '20px',
          fontWeight: '700',
          margin: '0 0 8px 0'
        }}>
          {welcomeTitle || 'Bienvenue !'}
        </h2>
        <p style={{
          color: 'rgba(255,255,255,0.5)',
          fontSize: '14px',
          margin: 0
        }}>
          Quelques infos avant de démarrer la conversation
        </p>
      </div>

      {/* Barre de progression */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        marginBottom: '32px',
        width: '100%',
        maxWidth: '280px'
      }}>
        {STEPS.map((s, i) => (
          <React.Fragment key={s.id}>
            <div style={{
              width: '36px',
              height: '36px',
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '14px',
              fontWeight: '700',
              transition: 'all 0.3s ease',
              background: s.id <= currentStep
                ? 'linear-gradient(135deg, #D91CD2, #8b5cf6)'
                : 'rgba(255,255,255,0.1)',
              color: s.id <= currentStep ? '#fff' : 'rgba(255,255,255,0.3)',
              border: s.id === currentStep
                ? '2px solid #D91CD2'
                : '2px solid transparent',
              boxShadow: s.id === currentStep
                ? '0 0 16px rgba(217, 28, 210, 0.4)'
                : 'none'
            }}>
              {s.id < currentStep ? '✓' : s.id}
            </div>
            {i < STEPS.length - 1 && (
              <div style={{
                flex: 1,
                height: '3px',
                borderRadius: '2px',
                transition: 'all 0.3s ease',
                background: s.id < currentStep
                  ? 'linear-gradient(90deg, #D91CD2, #8b5cf6)'
                  : 'rgba(255,255,255,0.1)'
              }} />
            )}
          </React.Fragment>
        ))}
      </div>

      {/* Champ actuel */}
      <div style={{
        width: '100%',
        maxWidth: '320px',
        marginBottom: '24px'
      }}>
        <label style={{
          display: 'block',
          color: '#ffffff',
          fontSize: '15px',
          fontWeight: '600',
          marginBottom: '10px'
        }}>
          <span style={{ marginRight: '8px' }}>{step.icon}</span>
          {step.label}
        </label>
        <input
          type={step.type}
          value={formData[step.field]}
          onChange={(e) => {
            setFormData(prev => ({ ...prev, [step.field]: e.target.value }));
            setError('');
          }}
          onKeyPress={handleKeyPress}
          placeholder={step.placeholder}
          autoFocus
          style={{
            width: '100%',
            padding: '14px 16px',
            borderRadius: '12px',
            border: error
              ? '2px solid #ef4444'
              : '2px solid rgba(255,255,255,0.15)',
            background: 'rgba(0,0,0,0.4)',
            color: '#ffffff',
            fontSize: '16px',
            outline: 'none',
            transition: 'border-color 0.2s ease',
            boxSizing: 'border-box'
          }}
          onFocus={(e) => {
            if (!error) e.target.style.borderColor = '#D91CD2';
          }}
          onBlur={(e) => {
            if (!error) e.target.style.borderColor = 'rgba(255,255,255,0.15)';
          }}
        />
        {error && (
          <p style={{
            color: '#ef4444',
            fontSize: '13px',
            marginTop: '6px',
            margin: '6px 0 0 0'
          }}>
            {error}
          </p>
        )}
      </div>

      {/* Boutons */}
      <div style={{
        display: 'flex',
        gap: '12px',
        width: '100%',
        maxWidth: '320px'
      }}>
        {currentStep > 1 && (
          <button
            onClick={handleBack}
            disabled={loading}
            style={{
              padding: '14px 20px',
              borderRadius: '12px',
              border: '1px solid rgba(255,255,255,0.2)',
              background: 'transparent',
              color: 'rgba(255,255,255,0.7)',
              fontSize: '15px',
              fontWeight: '600',
              cursor: loading ? 'not-allowed' : 'pointer',
              transition: 'all 0.2s ease',
              opacity: loading ? 0.5 : 1
            }}
          >
            ← Retour
          </button>
        )}
        <button
          onClick={handleNext}
          disabled={loading || !formData[step.field]?.trim()}
          style={{
            flex: 1,
            padding: '14px 24px',
            borderRadius: '12px',
            border: 'none',
            background: (!formData[step.field]?.trim() || loading)
              ? 'rgba(255,255,255,0.1)'
              : 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
            color: '#ffffff',
            fontSize: '15px',
            fontWeight: '700',
            cursor: (!formData[step.field]?.trim() || loading) ? 'not-allowed' : 'pointer',
            transition: 'all 0.2s ease',
            boxShadow: (!formData[step.field]?.trim() || loading)
              ? 'none'
              : '0 4px 20px rgba(217, 28, 210, 0.4)',
            opacity: (!formData[step.field]?.trim() || loading) ? 0.5 : 1
          }}
        >
          {loading ? '⏳ Connexion...' : currentStep === 3 ? '🚀 Commencer le chat' : 'Suivant →'}
        </button>
      </div>

      {/* Footer discret */}
      <p style={{
        color: 'rgba(255,255,255,0.2)',
        fontSize: '11px',
        marginTop: '24px',
        textAlign: 'center'
      }}>
        Étape {currentStep} sur 3 • Vos données sont protégées
      </p>
    </div>
  );
};

export default OnboardingTunnel;

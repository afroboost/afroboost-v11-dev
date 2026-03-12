// OnboardingTunnel.js — v98.2: Tunnel d'onboarding dynamique
// Charge les tunnel_questions du lien AVANT d'afficher le formulaire
// Fallback: 3 étapes par défaut (Nom, WhatsApp, Email) si aucune question configurée

import React, { useState, useCallback, useEffect } from 'react';

const DEFAULT_STEPS = [
  { id: 1, label: 'Votre nom', field: 'name', type: 'text', placeholder: 'Ex: Marie Dupont', icon: '👤' },
  { id: 2, label: 'Votre WhatsApp', field: 'whatsapp', type: 'tel', placeholder: 'Ex: +41 79 123 45 67', icon: '📱' },
  { id: 3, label: 'Votre email', field: 'email', type: 'email', placeholder: 'Ex: marie@gmail.com', icon: '✉️' }
];

const TYPE_ICONS = {
  text: '✏️', buttons: '🔘', email: '📧', phone: '📱', city: '📍', number: '🔢', date: '📅'
};

const OnboardingTunnel = ({ linkToken, onComplete, welcomeTitle }) => {
  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState({ name: '', whatsapp: '', email: '' });
  const [tunnelAnswers, setTunnelAnswers] = useState({});
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [linkData, setLinkData] = useState(null);
  const [fetchingLink, setFetchingLink] = useState(true);

  const API = (process.env.REACT_APP_BACKEND_URL || '') + '/api';

  // Fetch link data on mount to get tunnel_questions
  useEffect(() => {
    if (!linkToken) { setFetchingLink(false); return; }
    const fetchLink = async () => {
      try {
        const res = await fetch(`${API}/chat/links/${linkToken}`);
        if (res.ok) {
          const data = await res.json();
          setLinkData(data);
          console.log('[ONBOARDING] Link data loaded:', data.title, 'questions:', (data.tunnel_questions || []).length);
        }
      } catch (e) {
        console.error('[ONBOARDING] Erreur fetch link:', e);
      }
      setFetchingLink(false);
    };
    fetchLink();
  }, [linkToken, API]);

  // Build steps: default contact steps + custom tunnel questions
  const tunnelQuestions = (linkData?.tunnel_questions || []).filter(q => q.text && q.text.trim());
  const hasTunnel = tunnelQuestions.length > 0;

  // Steps = default 3 + custom questions
  const allSteps = [
    ...DEFAULT_STEPS,
    ...tunnelQuestions.map((q, i) => ({
      id: DEFAULT_STEPS.length + 1 + i,
      label: q.text,
      field: `tunnel_q_${i}`,
      type: q.type || 'text',
      placeholder: q.type === 'buttons' ? 'Choisissez une option' : 'Votre réponse...',
      icon: TYPE_ICONS[q.type] || '✏️',
      options: q.options || [],
      isTunnelQuestion: true,
    }))
  ];

  const totalSteps = allSteps.length;
  const step = allSteps[currentStep - 1];

  const welcomeMsg = linkData?.welcome_message || welcomeTitle || 'Bienvenue !';

  const getCurrentValue = () => {
    if (!step) return '';
    if (step.isTunnelQuestion) return tunnelAnswers[step.field] || '';
    return formData[step.field] || '';
  };

  const setCurrentValue = (val) => {
    if (step.isTunnelQuestion) {
      setTunnelAnswers(prev => ({ ...prev, [step.field]: val }));
    } else {
      setFormData(prev => ({ ...prev, [step.field]: val }));
    }
    setError('');
  };

  const validateStep = useCallback((stepObj, value) => {
    if (!value || !value.trim()) return 'Ce champ est requis';
    if (stepObj.field === 'whatsapp') {
      const cleaned = value.replace(/[\s\-().]/g, '');
      if (cleaned.length < 8) return 'Numéro trop court';
      if (!/^[+]?\d+$/.test(cleaned)) return 'Format invalide';
    }
    if (stepObj.field === 'email' || stepObj.type === 'email') {
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())) return 'Email invalide';
    }
    if (stepObj.type === 'phone') {
      const cleaned = value.replace(/[\s\-().]/g, '');
      if (cleaned.length < 8) return 'Numéro trop court';
    }
    return null;
  }, []);

  const handleNext = useCallback(async () => {
    const value = getCurrentValue();
    const validationError = validateStep(step, value);

    if (validationError) {
      setError(validationError);
      return;
    }
    setError('');

    if (currentStep < totalSteps) {
      setCurrentStep(prev => prev + 1);
      return;
    }

    // Last step → call smart-entry
    setLoading(true);
    try {
      // Build tunnel answers for submission
      const tunnelData = {};
      tunnelQuestions.forEach((q, i) => {
        tunnelData[`q_${i}`] = { question: q.text, answer: tunnelAnswers[`tunnel_q_${i}`] || '' };
      });

      const response = await fetch(`${API}/chat/smart-entry`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formData.name.trim(),
          email: formData.email.trim(),
          whatsapp: formData.whatsapp.trim(),
          link_token: linkToken,
          tunnel_answers: Object.keys(tunnelData).length > 0 ? tunnelData : undefined,
        })
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Erreur serveur');
      }

      const data = await response.json();
      const participantId = data.participant?.id || data.participant_id;
      const sessionId = data.session?.id || data.session_id;

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
        whatsapp: formData.whatsapp.trim(),
        tunnelAnswers: tunnelData,
      });
    } catch (err) {
      console.error('[ONBOARDING] Erreur smart-entry:', err);
      setError(err.message || 'Impossible de continuer. Réessayez.');
    } finally {
      setLoading(false);
    }
  }, [currentStep, totalSteps, formData, tunnelAnswers, linkToken, onComplete, step, tunnelQuestions, API, getCurrentValue, validateStep]);

  const handleBack = useCallback(() => {
    if (currentStep > 1) { setCurrentStep(prev => prev - 1); setError(''); }
  }, [currentStep]);

  const handleKeyPress = useCallback((e) => {
    if (e.key === 'Enter') { e.preventDefault(); handleNext(); }
  }, [handleNext]);

  // Loading state
  if (fetchingLink) {
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        padding: '48px 24px', minHeight: '300px',
        background: 'linear-gradient(180deg, #0a0a0a 0%, #1a0a1a 100%)',
        borderRadius: '16px', width: '100%', maxWidth: '420px', margin: '0 auto',
      }}>
        <div style={{ fontSize: '32px', marginBottom: '16px', animation: 'pulse 1.5s infinite' }}>💬</div>
        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '14px' }}>Chargement...</p>
      </div>
    );
  }

  const currentValue = getCurrentValue();
  const isButtonsType = step?.type === 'buttons' && step?.options?.length > 0;
  const isLastStep = currentStep === totalSteps;

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      padding: '32px 24px', minHeight: '400px',
      background: 'linear-gradient(180deg, #0a0a0a 0%, #1a0a1a 100%)',
      borderRadius: '16px', width: '100%', maxWidth: '420px', margin: '0 auto'
    }}>
      {/* Logo / Titre */}
      <div style={{ textAlign: 'center', marginBottom: '32px' }}>
        <div style={{ fontSize: '36px', marginBottom: '8px' }}>💬</div>
        <h2 style={{ color: '#ffffff', fontSize: '20px', fontWeight: '700', margin: '0 0 8px 0' }}>
          {welcomeMsg}
        </h2>
        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '14px', margin: 0 }}>
          {hasTunnel ? `${totalSteps} étapes pour personnaliser votre expérience` : 'Quelques infos avant de démarrer la conversation'}
        </p>
      </div>

      {/* Barre de progression */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '4px',
        marginBottom: '32px', width: '100%', maxWidth: '320px'
      }}>
        {allSteps.map((s, i) => (
          <div key={s.id} style={{
            flex: 1, height: '4px', borderRadius: '2px',
            transition: 'all 0.3s ease',
            background: i + 1 <= currentStep
              ? 'linear-gradient(90deg, #D91CD2, #8b5cf6)'
              : 'rgba(255,255,255,0.1)',
          }} />
        ))}
      </div>

      {/* Step counter */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px',
      }}>
        <div style={{
          width: '28px', height: '28px', borderRadius: '50%',
          background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontSize: '12px', fontWeight: '700',
          boxShadow: '0 0 12px rgba(217,28,210,0.4)',
        }}>
          {currentStep}
        </div>
        <span style={{ color: 'rgba(255,255,255,0.35)', fontSize: '12px' }}>/ {totalSteps}</span>
      </div>

      {/* Champ actuel */}
      <div style={{ width: '100%', maxWidth: '320px', marginBottom: '24px' }}>
        <label style={{
          display: 'block', color: '#ffffff', fontSize: '15px', fontWeight: '600', marginBottom: '10px'
        }}>
          <span style={{ marginRight: '8px' }}>{step.icon}</span>
          {step.label}
        </label>

        {isButtonsType ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {step.options.map((opt, oi) => (
              <button
                key={oi}
                onClick={() => setCurrentValue(opt)}
                style={{
                  padding: '12px 16px', borderRadius: '12px',
                  background: currentValue === opt ? 'rgba(217,28,210,0.15)' : 'rgba(255,255,255,0.04)',
                  border: currentValue === opt ? '2px solid #D91CD2' : '2px solid rgba(255,255,255,0.12)',
                  color: currentValue === opt ? '#D91CD2' : '#ffffff',
                  fontSize: '15px', fontWeight: currentValue === opt ? '700' : '500',
                  cursor: 'pointer', textAlign: 'left',
                  transition: 'all 0.2s ease',
                  boxShadow: currentValue === opt ? '0 0 12px rgba(217,28,210,0.2)' : 'none',
                }}
              >
                {opt}
              </button>
            ))}
          </div>
        ) : (
          <input
            type={step.type === 'city' ? 'text' : step.type === 'buttons' ? 'text' : step.type}
            value={currentValue}
            onChange={(e) => setCurrentValue(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={step.placeholder}
            autoFocus
            style={{
              width: '100%', padding: '14px 16px', borderRadius: '12px',
              border: error ? '2px solid #ef4444' : '2px solid rgba(255,255,255,0.15)',
              background: 'rgba(0,0,0,0.4)', color: '#ffffff', fontSize: '16px',
              outline: 'none', transition: 'border-color 0.2s ease', boxSizing: 'border-box'
            }}
            onFocus={(e) => { if (!error) e.target.style.borderColor = '#D91CD2'; }}
            onBlur={(e) => { if (!error) e.target.style.borderColor = 'rgba(255,255,255,0.15)'; }}
          />
        )}
        {error && (
          <p style={{ color: '#ef4444', fontSize: '13px', margin: '6px 0 0 0' }}>{error}</p>
        )}
      </div>

      {/* Boutons */}
      <div style={{ display: 'flex', gap: '12px', width: '100%', maxWidth: '320px' }}>
        {currentStep > 1 && (
          <button
            onClick={handleBack}
            disabled={loading}
            style={{
              padding: '14px 20px', borderRadius: '12px',
              border: '1px solid rgba(255,255,255,0.2)',
              background: 'transparent', color: 'rgba(255,255,255,0.7)',
              fontSize: '15px', fontWeight: '600',
              cursor: loading ? 'not-allowed' : 'pointer',
              transition: 'all 0.2s ease', opacity: loading ? 0.5 : 1
            }}
          >
            ← Retour
          </button>
        )}
        <button
          onClick={handleNext}
          disabled={loading || !currentValue?.trim()}
          style={{
            flex: 1, padding: '14px 24px', borderRadius: '12px', border: 'none',
            background: (!currentValue?.trim() || loading) ? 'rgba(255,255,255,0.1)' : 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
            color: '#ffffff', fontSize: '15px', fontWeight: '700',
            cursor: (!currentValue?.trim() || loading) ? 'not-allowed' : 'pointer',
            transition: 'all 0.2s ease',
            boxShadow: (!currentValue?.trim() || loading) ? 'none' : '0 4px 20px rgba(217, 28, 210, 0.4)',
            opacity: (!currentValue?.trim() || loading) ? 0.5 : 1
          }}
        >
          {loading ? '⏳ Connexion...' : isLastStep ? '🚀 Commencer le chat' : 'Suivant →'}
        </button>
      </div>

      {/* Footer */}
      <p style={{
        color: 'rgba(255,255,255,0.2)', fontSize: '11px', marginTop: '24px', textAlign: 'center'
      }}>
        Étape {currentStep} sur {totalSteps} • Vos données sont protégées
      </p>
    </div>
  );
};

export default OnboardingTunnel;

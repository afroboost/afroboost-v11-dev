// LinkSimulator.js — v99: Aperçu du tunnel de chat en direct
// Panneau de simulation qui montre comment le visiteur verra le tunnel
// Utilise le logo Afroboost officiel (/logo192.png)

import React, { useState, memo, useEffect } from 'react';
import { Eye, Play, RotateCcw, Smartphone, Monitor, X } from 'lucide-react';

const GLOW = {
  violet: '0 0 12px rgba(217, 28, 210, 0.5), 0 0 24px rgba(217, 28, 210, 0.2)',
};

// === Simulated Tunnel Step ===
const SimStep = ({ question, type, options, stepNum, totalSteps, active, onAnswer }) => {
  const [value, setValue] = useState('');

  if (!active) return null;

  return (
    <div style={{
      animation: 'fadeInUp 0.3s ease',
      display: 'flex', flexDirection: 'column', gap: '12px',
    }}>
      {/* Step counter */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <div style={{
          width: '24px', height: '24px', borderRadius: '50%',
          background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontSize: '10px', fontWeight: '700',
        }}>
          {stepNum}
        </div>
        <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '11px' }}>
          / {totalSteps}
        </span>
      </div>

      {/* Question */}
      <p style={{ color: '#fff', fontSize: '14px', fontWeight: '600', margin: 0 }}>
        {question}
      </p>

      {/* Input based on type */}
      {type === 'buttons' && options?.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {options.map((opt, i) => (
            <button
              key={i}
              onClick={() => { setValue(opt); setTimeout(() => onAnswer(opt), 300); }}
              style={{
                padding: '10px 14px', borderRadius: '10px',
                background: value === opt ? 'rgba(217,28,210,0.15)' : 'rgba(255,255,255,0.04)',
                border: value === opt ? '1.5px solid #D91CD2' : '1.5px solid rgba(255,255,255,0.1)',
                color: value === opt ? '#D91CD2' : '#fff',
                fontSize: '13px', fontWeight: value === opt ? '600' : '400',
                cursor: 'pointer', textAlign: 'left', transition: 'all 0.2s',
              }}
            >
              {opt}
            </button>
          ))}
        </div>
      ) : (
        <div style={{ display: 'flex', gap: '8px' }}>
          <input
            type={type === 'email' ? 'email' : type === 'phone' || type === 'tel' ? 'tel' : 'text'}
            value={value}
            onChange={e => setValue(e.target.value)}
            placeholder={
              type === 'email' ? 'email@exemple.com' :
              type === 'phone' || type === 'tel' ? '+41 79 123 45 67' :
              type === 'city' ? 'Votre ville...' :
              'Votre réponse...'
            }
            style={{
              flex: 1, padding: '10px 14px', borderRadius: '10px',
              background: 'rgba(0,0,0,0.3)', border: '1.5px solid rgba(255,255,255,0.1)',
              color: '#fff', fontSize: '13px', outline: 'none',
            }}
            onFocus={e => e.target.style.borderColor = '#D91CD2'}
            onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.1)'}
          />
          <button
            onClick={() => value.trim() && onAnswer(value)}
            disabled={!value.trim()}
            style={{
              padding: '10px 16px', borderRadius: '10px',
              background: value.trim() ? 'linear-gradient(135deg, #D91CD2, #8b5cf6)' : 'rgba(255,255,255,0.06)',
              border: 'none', color: '#fff', fontSize: '12px', fontWeight: '600',
              cursor: value.trim() ? 'pointer' : 'not-allowed',
              opacity: value.trim() ? 1 : 0.4,
            }}
          >
            →
          </button>
        </div>
      )}
    </div>
  );
};

// === Main LinkSimulator ===
const LinkSimulator = memo(({ link, isOpen, onClose }) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [answers, setAnswers] = useState([]);
  const [viewMode, setViewMode] = useState('mobile'); // 'mobile' | 'desktop'
  const [completed, setCompleted] = useState(false);

  // Default steps + custom tunnel questions
  const defaultSteps = [
    { text: 'Votre nom', type: 'text', options: [] },
    { text: 'Votre WhatsApp', type: 'phone', options: [] },
    { text: 'Votre email', type: 'email', options: [] },
  ];

  const tunnelQuestions = (link?.tunnel_questions || []).filter(q => q.text?.trim());
  const allSteps = [...defaultSteps, ...tunnelQuestions];
  const welcomeMessage = link?.welcome_message || 'Bienvenue !';

  const handleAnswer = (answer) => {
    setAnswers(prev => [...prev, { step: currentStep, answer }]);
    if (currentStep < allSteps.length - 1) {
      setCurrentStep(prev => prev + 1);
    } else {
      setCompleted(true);
    }
  };

  const handleReset = () => {
    setCurrentStep(0);
    setAnswers([]);
    setCompleted(false);
  };

  useEffect(() => {
    if (isOpen) handleReset();
  }, [isOpen, link]);

  if (!isOpen) return null;

  const phoneWidth = viewMode === 'mobile' ? '340px' : '100%';

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 10000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)',
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{
        width: '100%', maxWidth: '500px',
        display: 'flex', flexDirection: 'column', gap: '12px',
      }}>
        {/* Toolbar */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '0 4px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Eye size={16} color="#D91CD2" />
            <span style={{ color: '#fff', fontSize: '13px', fontWeight: '600' }}>
              Aperçu : {link?.title || 'Lien'}
            </span>
          </div>
          <div style={{ display: 'flex', gap: '6px' }}>
            <button onClick={() => setViewMode('mobile')} style={{
              padding: '6px 10px', borderRadius: '8px',
              background: viewMode === 'mobile' ? 'rgba(217,28,210,0.2)' : 'rgba(255,255,255,0.06)',
              border: viewMode === 'mobile' ? '1px solid rgba(217,28,210,0.4)' : '1px solid rgba(255,255,255,0.1)',
              color: viewMode === 'mobile' ? '#D91CD2' : 'rgba(255,255,255,0.4)',
              cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px',
              fontSize: '11px', fontWeight: '600',
            }}>
              <Smartphone size={12} /> Mobile
            </button>
            <button onClick={() => setViewMode('desktop')} style={{
              padding: '6px 10px', borderRadius: '8px',
              background: viewMode === 'desktop' ? 'rgba(217,28,210,0.2)' : 'rgba(255,255,255,0.06)',
              border: viewMode === 'desktop' ? '1px solid rgba(217,28,210,0.4)' : '1px solid rgba(255,255,255,0.1)',
              color: viewMode === 'desktop' ? '#D91CD2' : 'rgba(255,255,255,0.4)',
              cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px',
              fontSize: '11px', fontWeight: '600',
            }}>
              <Monitor size={12} /> Desktop
            </button>
            <button onClick={handleReset} style={{
              padding: '6px 10px', borderRadius: '8px',
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.1)',
              color: 'rgba(255,255,255,0.4)', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '4px',
              fontSize: '11px',
            }}>
              <RotateCcw size={12} /> Reset
            </button>
            <button onClick={onClose} style={{
              padding: '6px', borderRadius: '8px',
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.1)',
              color: 'rgba(255,255,255,0.4)', cursor: 'pointer',
            }}>
              <X size={14} />
            </button>
          </div>
        </div>

        {/* Phone frame */}
        <div style={{
          width: phoneWidth, maxWidth: '100%', margin: '0 auto',
          background: '#0a0a0a',
          border: viewMode === 'mobile' ? '3px solid #333' : '1px solid rgba(255,255,255,0.1)',
          borderRadius: viewMode === 'mobile' ? '32px' : '12px',
          overflow: 'hidden',
          boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
          transition: 'all 0.3s ease',
        }}>
          {/* Status bar (mobile only) */}
          {viewMode === 'mobile' && (
            <div style={{
              padding: '8px 24px 4px', display: 'flex', justifyContent: 'space-between',
              fontSize: '11px', color: 'rgba(255,255,255,0.5)',
            }}>
              <span>9:41</span>
              <span>●●●●● Wi-Fi 🔋</span>
            </div>
          )}

          {/* Chat header */}
          <div style={{
            padding: '12px 16px',
            background: 'linear-gradient(135deg, rgba(217,28,210,0.08), rgba(139,92,246,0.04))',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
            display: 'flex', alignItems: 'center', gap: '10px',
          }}>
            <img
              src="/logo192.png"
              alt="Afroboost"
              style={{
                width: '32px', height: '32px', borderRadius: '50%',
                objectFit: 'cover',
                border: '2px solid rgba(217,28,210,0.3)',
              }}
            />
            <div>
              <p style={{ color: '#fff', fontSize: '13px', fontWeight: '700', margin: 0 }}>
                Afroboost
              </p>
              <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '10px', margin: 0 }}>
                En ligne
              </p>
            </div>
          </div>

          {/* Chat body */}
          <div style={{
            padding: '20px 16px',
            minHeight: viewMode === 'mobile' ? '380px' : '300px',
            display: 'flex', flexDirection: 'column', gap: '16px',
            background: 'linear-gradient(180deg, #0a0a0a 0%, #1a0a1a 100%)',
          }}>
            {/* Welcome message bubble */}
            <div style={{
              background: '#D91CD2',
              padding: '12px 16px', borderRadius: '16px 16px 16px 4px',
              maxWidth: '85%', fontSize: '13px', color: '#fff',
              boxShadow: '0 2px 8px rgba(217,28,210,0.3)',
            }}>
              {welcomeMessage}
            </div>

            {/* Answered steps */}
            {answers.map((a, i) => (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {/* AI question */}
                <div style={{
                  background: '#D91CD2', padding: '10px 14px',
                  borderRadius: '14px 14px 14px 4px',
                  maxWidth: '80%', fontSize: '12px', color: '#fff',
                  opacity: 0.7,
                }}>
                  {allSteps[a.step]?.text}
                </div>
                {/* User answer */}
                <div style={{
                  background: '#2A2A2A', padding: '10px 14px',
                  borderRadius: '14px 14px 4px 14px',
                  maxWidth: '75%', fontSize: '12px', color: '#fff',
                  alignSelf: 'flex-end',
                }}>
                  {a.answer}
                </div>
              </div>
            ))}

            {/* Current step */}
            {!completed && (
              <SimStep
                question={allSteps[currentStep]?.text}
                type={allSteps[currentStep]?.type}
                options={allSteps[currentStep]?.options}
                stepNum={currentStep + 1}
                totalSteps={allSteps.length}
                active={true}
                onAnswer={handleAnswer}
              />
            )}

            {/* Completion */}
            {completed && (
              <div style={{
                textAlign: 'center', padding: '24px 16px',
                background: 'rgba(34,197,94,0.06)',
                border: '1px solid rgba(34,197,94,0.2)',
                borderRadius: '12px',
              }}>
                <div style={{ fontSize: '32px', marginBottom: '8px' }}>✅</div>
                <p style={{ color: '#22c55e', fontSize: '14px', fontWeight: '700', margin: 0 }}>
                  Tunnel terminé !
                </p>
                <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px', margin: '6px 0 0' }}>
                  Le visiteur serait maintenant redirigé vers le chat IA
                </p>
              </div>
            )}
          </div>

          {/* Progress bar */}
          <div style={{
            height: '3px',
            background: 'rgba(255,255,255,0.05)',
          }}>
            <div style={{
              height: '100%',
              width: `${((currentStep + (completed ? 1 : 0)) / allSteps.length) * 100}%`,
              background: 'linear-gradient(90deg, #D91CD2, #8b5cf6)',
              transition: 'width 0.3s ease',
              borderRadius: '0 2px 2px 0',
            }} />
          </div>
        </div>

        {/* Stats bar */}
        <div style={{
          display: 'flex', justifyContent: 'center', gap: '16px',
          padding: '4px', fontSize: '11px', color: 'rgba(255,255,255,0.3)',
        }}>
          <span>📊 {allSteps.length} étapes</span>
          <span>|</span>
          <span>✅ {answers.length} réponses</span>
          <span>|</span>
          <span>{tunnelQuestions.length > 0 ? `🧩 ${tunnelQuestions.length} questions custom` : '📋 Questions par défaut'}</span>
        </div>
      </div>
    </div>
  );
});

LinkSimulator.displayName = 'LinkSimulator';
export default LinkSimulator;

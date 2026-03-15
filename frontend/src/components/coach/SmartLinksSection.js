// SmartLinksSection.js — v98.2: Liens Intelligents de Conversion
// Multi-sélection, bulk delete, Stratégie IA, design premium anthracite
// Fix: robust ID chain, delete fonctionne, tunnel questions visibles

import React, { useState, useRef, memo, useCallback, useEffect } from 'react';
import { Link2, Copy, Check, ExternalLink, Trash2, Edit2, Save, X, Plus, ChevronDown, ChevronUp, Users, MessageCircle, Calendar, CreditCard, Phone, Target, Zap, BarChart3, Eye, Play, ArrowRight, GripVertical, Sparkles, CheckSquare, Square } from 'lucide-react';
import SmartLinkCard from './SmartLinkCard';
import LinkSimulator from './LinkSimulator';

// ====== STYLES ======
const GLOW = {
  violet: '0 0 12px rgba(217, 28, 210, 0.5), 0 0 24px rgba(217, 28, 210, 0.2)',
  violetSoft: '0 0 8px rgba(217, 28, 210, 0.3)',
  green: '0 0 12px rgba(34, 197, 94, 0.5)',
  red: '0 0 8px rgba(239, 68, 68, 0.4)',
  amber: '0 0 8px rgba(245, 158, 11, 0.4)',
  blue: '0 0 8px rgba(59, 130, 246, 0.4)',
};

const STEPS = [
  { id: 1, label: 'Infos & Prompt', icon: '🎯' },
  { id: 2, label: 'Tunnel', icon: '🧩' },
  { id: 3, label: 'Actions', icon: '⚡' },
];

const QUESTION_TYPES = [
  { value: 'text', label: 'Texte libre', icon: '✏️' },
  { value: 'buttons', label: 'Boutons choix', icon: '🔘' },
  { value: 'email', label: 'Email', icon: '📧' },
  { value: 'phone', label: 'Téléphone', icon: '📱' },
  { value: 'city', label: 'Ville', icon: '📍' },
  { value: 'number', label: 'Nombre', icon: '🔢' },
  { value: 'date', label: 'Date', icon: '📅' },
];

const LEAD_TYPES = [
  { value: 'participant', label: 'Participant', color: '#22c55e', icon: '🏃' },
  { value: 'partner', label: 'Partenaire', color: '#f59e0b', icon: '🤝' },
  { value: 'collaboration', label: 'Collaboration', color: '#3b82f6', icon: '🎯' },
  { value: 'group', label: 'Groupe', color: '#ec4899', icon: '👥' },
  { value: 'question', label: 'Question', color: '#a78bfa', icon: '❓' },
];

const ACTION_TYPES = [
  { value: 'booking', label: 'Réserver un créneau', icon: <Calendar size={16} />, color: '#22c55e' },
  { value: 'payment', label: 'Paiement', icon: <CreditCard size={16} />, color: '#f59e0b' },
  { value: 'callback', label: 'Demander un rappel', icon: <Phone size={16} />, color: '#3b82f6' },
  { value: 'redirect', label: 'Rediriger vers lien', icon: <ExternalLink size={16} />, color: '#a78bfa' },
];

// ====== MODAL DE CRÉATION DE LIEN INTELLIGENT ======
const SmartLinkModal = memo(({ isOpen, onClose, onSave, editingLink, API, coachEmail }) => {
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [linkData, setLinkData] = useState(() => editingLink ? {
    title: editingLink.title || '',
    custom_prompt: editingLink.custom_prompt || '',
    lead_type: editingLink.lead_type || 'participant',
    tunnel_questions: editingLink.tunnel_questions || [],
    end_actions: editingLink.end_actions || [],
    welcome_message: editingLink.welcome_message || '',
  } : {
    title: '',
    custom_prompt: '',
    lead_type: 'participant',
    tunnel_questions: [],
    end_actions: [],
    welcome_message: '',
  });

  // v100: Sync linkData quand editingLink change (fix: champs vides en modification)
  useEffect(() => {
    if (editingLink) {
      setLinkData({
        title: editingLink.title || '',
        custom_prompt: editingLink.custom_prompt || '',
        lead_type: editingLink.lead_type || 'participant',
        tunnel_questions: editingLink.tunnel_questions || [],
        end_actions: editingLink.end_actions || [],
        welcome_message: editingLink.welcome_message || '',
      });
      setStep(1);
    } else {
      setLinkData({
        title: '', custom_prompt: '', lead_type: 'participant',
        tunnel_questions: [], end_actions: [], welcome_message: '',
      });
      setStep(1);
    }
  }, [editingLink]);

  const updateField = (field, value) => setLinkData(prev => ({ ...prev, [field]: value }));

  // === Gestion des questions du tunnel ===
  const addQuestion = () => {
    updateField('tunnel_questions', [
      ...linkData.tunnel_questions,
      { id: Date.now(), text: '', type: 'text', options: [], required: true }
    ]);
  };

  const updateQuestion = (idx, field, value) => {
    const updated = [...linkData.tunnel_questions];
    updated[idx] = { ...updated[idx], [field]: value };
    updateField('tunnel_questions', updated);
  };

  const removeQuestion = (idx) => {
    updateField('tunnel_questions', linkData.tunnel_questions.filter((_, i) => i !== idx));
  };

  const addOption = (qIdx) => {
    const updated = [...linkData.tunnel_questions];
    updated[qIdx].options = [...(updated[qIdx].options || []), ''];
    updateField('tunnel_questions', updated);
  };

  const updateOption = (qIdx, oIdx, value) => {
    const updated = [...linkData.tunnel_questions];
    updated[qIdx].options[oIdx] = value;
    updateField('tunnel_questions', updated);
  };

  const removeOption = (qIdx, oIdx) => {
    const updated = [...linkData.tunnel_questions];
    updated[qIdx].options = updated[qIdx].options.filter((_, i) => i !== oIdx);
    updateField('tunnel_questions', updated);
  };

  // === Gestion des actions de fin ===
  const toggleAction = (actionValue) => {
    const current = linkData.end_actions || [];
    if (current.find(a => a.type === actionValue)) {
      updateField('end_actions', current.filter(a => a.type !== actionValue));
    } else {
      updateField('end_actions', [...current, { type: actionValue, config: {} }]);
    }
  };

  // === Stratégie IA ===
  const [aiLoading, setAiLoading] = useState(false);
  const [aiObjective, setAiObjective] = useState('');
  const [showAiPanel, setShowAiPanel] = useState(false);

  const generateAiStrategy = async () => {
    if (!aiObjective.trim()) return;
    setAiLoading(true);
    try {
      const res = await fetch(`${API}/chat/generate-strategy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-Email': coachEmail },
        body: JSON.stringify({ objective: aiObjective.trim(), lead_type: linkData.lead_type }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.questions && data.questions.length > 0) {
          updateField('tunnel_questions', data.questions.map((q, i) => ({
            id: Date.now() + i, text: q.text || q, type: q.type || 'text',
            options: q.options || [], required: true,
          })));
        }
        if (data.welcome_message) updateField('welcome_message', data.welcome_message);
        if (data.custom_prompt) updateField('custom_prompt', data.custom_prompt);
        setShowAiPanel(false);
        setAiObjective('');
      }
    } catch (e) {
      console.error('[AI Strategy] Error:', e);
    }
    setAiLoading(false);
  };

  // === Validation ===
  const canGoNext = () => {
    if (step === 1) return linkData.title.trim().length > 0;
    if (step === 2) return true; // tunnel optionnel
    return true;
  };

  // === Sauvegarde ===
  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(linkData, editingLink?.id);
      onClose();
    } catch (e) {
      console.error('Erreur sauvegarde lien:', e);
    }
    setSaving(false);
  };

  if (!isOpen) return null;

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(8px)',
    }} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={{
        width: '100%', maxWidth: '620px', maxHeight: '90vh',
        background: 'linear-gradient(135deg, #1a1025 0%, #0d0a14 100%)',
        border: '1px solid rgba(217, 28, 210, 0.25)',
        borderRadius: '16px',
        display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
        boxShadow: '0 24px 48px rgba(0,0,0,0.4)',
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 20px',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: '32px', height: '32px', borderRadius: '10px',
              background: 'linear-gradient(135deg, #D91CD2, #9333ea)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Link2 size={16} color="#fff" />
            </div>
            <span style={{ color: '#fff', fontSize: '16px', fontWeight: '700' }}>
              {editingLink ? '✏️ Modifier le lien' : '🔗 Nouveau Lien Intelligent'}
            </span>
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)',
            cursor: 'pointer', padding: '4px',
          }}>
            <X size={20} />
          </button>
        </div>

        {/* Stepper */}
        <div style={{ display: 'flex', padding: '12px 20px', gap: '8px' }}>
          {STEPS.map(s => (
            <div
              key={s.id}
              onClick={() => { if (s.id < step || canGoNext()) setStep(s.id); }}
              style={{
                flex: 1, padding: '8px', borderRadius: '10px',
                background: step === s.id
                  ? 'rgba(217, 28, 210, 0.2)'
                  : step > s.id
                    ? 'rgba(34, 197, 94, 0.12)'
                    : 'rgba(255,255,255,0.03)',
                border: step === s.id
                  ? '1px solid rgba(217, 28, 210, 0.4)'
                  : step > s.id
                    ? '1px solid rgba(34, 197, 94, 0.2)'
                    : '1px solid rgba(255,255,255,0.06)',
                cursor: 'pointer',
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px',
                transition: 'all 0.2s',
              }}
            >
              <span style={{ fontSize: '14px' }}>{s.icon}</span>
              <span style={{ fontSize: '10px', fontWeight: '600', color: step >= s.id ? '#c4b5fd' : 'rgba(255,255,255,0.3)' }}>
                {s.label}
              </span>
            </div>
          ))}
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>

          {/* ====== STEP 1: Infos & Prompt ====== */}
          {step === 1 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Nom du lien */}
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#D91CD2', fontWeight: '600', marginBottom: '8px' }}>
                  Nom du lien *
                </label>
                <input
                  value={linkData.title}
                  onChange={e => updateField('title', e.target.value)}
                  placeholder="Ex: Offre Partenaire Mars 2026"
                  style={{
                    width: '100%', padding: '12px 16px',
                    background: 'rgba(255,255,255,0.04)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: '10px', color: '#fff', fontSize: '14px', outline: 'none',
                  }}
                  onFocus={e => e.target.style.borderColor = 'rgba(217,28,210,0.4)'}
                  onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.08)'}
                />
              </div>

              {/* Type de lead */}
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: '#D91CD2', fontWeight: '600', marginBottom: '10px' }}>
                  Type de lead
                </label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {LEAD_TYPES.map(lt => (
                    <button
                      key={lt.value}
                      onClick={() => updateField('lead_type', lt.value)}
                      style={{
                        padding: '8px 16px', borderRadius: '20px',
                        background: linkData.lead_type === lt.value
                          ? `${lt.color}22`
                          : 'rgba(255,255,255,0.04)',
                        border: linkData.lead_type === lt.value
                          ? `1px solid ${lt.color}66`
                          : '1px solid rgba(255,255,255,0.08)',
                        color: linkData.lead_type === lt.value ? lt.color : 'rgba(255,255,255,0.5)',
                        fontSize: '12px', fontWeight: '600', cursor: 'pointer',
                        display: 'flex', alignItems: 'center', gap: '6px',
                        transition: 'all 0.2s',
                      }}
                    >
                      <span>{lt.icon}</span> {lt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Message d'accueil */}
              <div>
                <label style={{ display: 'block', fontSize: '12px', color: 'rgba(255,255,255,0.5)', fontWeight: '600', marginBottom: '8px' }}>
                  💬 Message d'accueil (optionnel)
                </label>
                <textarea
                  value={linkData.welcome_message}
                  onChange={e => updateField('welcome_message', e.target.value)}
                  placeholder="Ex: Salut ! 👋 Bienvenue chez Afroboost. Je vais te poser quelques questions..."
                  rows={2}
                  style={{
                    width: '100%', padding: '12px 16px',
                    background: 'rgba(255,255,255,0.04)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: '10px', color: '#fff', fontSize: '13px',
                    outline: 'none', resize: 'vertical', fontFamily: 'inherit',
                    minHeight: '60px',
                  }}
                />
              </div>

              {/* Prompt Système IA */}
              <div style={{
                background: 'rgba(147, 51, 234, 0.06)',
                border: '1px solid rgba(147, 51, 234, 0.15)',
                borderRadius: '12px', padding: '16px',
              }}>
                <label style={{ display: 'block', fontSize: '12px', color: '#a78bfa', fontWeight: '600', marginBottom: '8px' }}>
                  🧠 Prompt Système (optionnel)
                </label>
                <textarea
                  value={linkData.custom_prompt}
                  onChange={e => updateField('custom_prompt', e.target.value)}
                  placeholder="Ex: Tu es un coach sportif motivant. Ton objectif est de qualifier le lead pour un abonnement partenaire."
                  rows={3}
                  style={{
                    width: '100%', padding: '12px 16px',
                    background: 'rgba(255,255,255,0.04)',
                    border: '1px solid rgba(139,92,246,0.2)',
                    borderRadius: '8px', color: '#fff', fontSize: '13px',
                    outline: 'none', resize: 'vertical', fontFamily: 'inherit',
                    minHeight: '70px',
                  }}
                />
              </div>
            </div>
          )}

          {/* ====== STEP 2: Tunnel Conversationnel ====== */}
          {step === 2 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <p style={{ color: '#fff', fontSize: '14px', fontWeight: '600', margin: 0 }}>
                    Questions du tunnel
                  </p>
                  <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px', margin: '4px 0 0' }}>
                    L'IA posera ces questions dans l'ordre. Laissez vide pour un chat libre.
                  </p>
                </div>
                <button
                  onClick={addQuestion}
                  style={{
                    padding: '8px 16px', borderRadius: '20px',
                    background: 'linear-gradient(135deg, #D91CD2, #9333ea)',
                    border: 'none', color: '#fff', fontSize: '12px', fontWeight: '600',
                    cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px',
                    boxShadow: 'none', transition: 'all 0.2s',
                  }}
                  onMouseEnter={e => e.target.style.boxShadow = GLOW.violet}
                  onMouseLeave={e => e.target.style.boxShadow = 'none'}
                >
                  <Plus size={14} /> Ajouter
                </button>
              </div>

              {/* Bouton Stratégie IA */}
              <button
                onClick={() => setShowAiPanel(!showAiPanel)}
                style={{
                  width: '100%', padding: '12px 16px', borderRadius: '12px',
                  background: 'linear-gradient(135deg, rgba(139,92,246,0.12), rgba(217,28,210,0.08))',
                  border: '1px solid rgba(139,92,246,0.25)',
                  color: '#c4b5fd', fontSize: '13px', fontWeight: '600',
                  cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
                  transition: 'all 0.2s',
                }}
                onMouseEnter={e => { e.currentTarget.style.background = 'linear-gradient(135deg, rgba(139,92,246,0.2), rgba(217,28,210,0.15))'; e.currentTarget.style.boxShadow = '0 0 16px rgba(139,92,246,0.2)'; }}
                onMouseLeave={e => { e.currentTarget.style.background = 'linear-gradient(135deg, rgba(139,92,246,0.12), rgba(217,28,210,0.08))'; e.currentTarget.style.boxShadow = 'none'; }}
              >
                <Sparkles size={16} /> ✨ Générer une Stratégie IA
              </button>

              {/* Panel IA */}
              {showAiPanel && (
                <div style={{
                  background: 'rgba(139,92,246,0.06)',
                  border: '1px solid rgba(139,92,246,0.2)',
                  borderRadius: '12px', padding: '16px',
                }}>
                  <label style={{ display: 'block', fontSize: '12px', color: '#a78bfa', fontWeight: '600', marginBottom: '8px' }}>
                    🎯 Quel est votre objectif avec ce lien ?
                  </label>
                  <textarea
                    value={aiObjective}
                    onChange={e => setAiObjective(e.target.value)}
                    placeholder="Ex: Qualifier des prospects pour mon programme de coaching sportif à 150 CHF/mois. Je veux connaître leur niveau, objectifs et disponibilités."
                    rows={3}
                    style={{
                      width: '100%', padding: '10px 14px',
                      background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(139,92,246,0.15)',
                      borderRadius: '8px', color: '#fff', fontSize: '13px',
                      outline: 'none', resize: 'vertical', fontFamily: 'inherit',
                      boxSizing: 'border-box',
                    }}
                  />
                  <button
                    onClick={generateAiStrategy}
                    disabled={aiLoading || !aiObjective.trim()}
                    style={{
                      marginTop: '10px', padding: '10px 20px', borderRadius: '10px',
                      background: aiLoading || !aiObjective.trim() ? 'rgba(139,92,246,0.15)' : 'linear-gradient(135deg, #8b5cf6, #D91CD2)',
                      border: 'none', color: '#fff', fontSize: '12px', fontWeight: '700',
                      cursor: aiLoading || !aiObjective.trim() ? 'not-allowed' : 'pointer',
                      opacity: aiLoading || !aiObjective.trim() ? 0.5 : 1,
                      display: 'flex', alignItems: 'center', gap: '6px',
                    }}
                  >
                    {aiLoading ? '⏳ Génération en cours...' : '🚀 Générer le tunnel'}
                  </button>
                  <p style={{ color: 'rgba(139,92,246,0.5)', fontSize: '10px', marginTop: '8px', margin: '8px 0 0' }}>
                    L'IA va créer des questions personnalisées, un message d'accueil et un prompt système adaptés à votre objectif.
                  </p>
                </div>
              )}

              {linkData.tunnel_questions.length === 0 && !showAiPanel && (
                <div style={{
                  padding: '32px', textAlign: 'center',
                  border: '2px dashed rgba(217,28,210,0.2)',
                  borderRadius: '12px',
                }}>
                  <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: '13px', margin: 0 }}>
                    🧩 Aucune question ajoutée
                  </p>
                  <p style={{ color: 'rgba(255,255,255,0.2)', fontSize: '11px', margin: '6px 0 0' }}>
                    Utilisez le bouton "Stratégie IA" ou ajoutez manuellement
                  </p>
                </div>
              )}

              {/* Questions list */}
              {linkData.tunnel_questions.map((q, idx) => (
                <div key={q.id} style={{
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid rgba(217,28,210,0.12)',
                  borderRadius: '12px', padding: '16px',
                  transition: 'border-color 0.2s',
                }}>
                  {/* Header question */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
                    <div style={{
                      width: '24px', height: '24px', borderRadius: '50%',
                      background: 'linear-gradient(135deg, #D91CD2, #9333ea)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: '#fff', fontSize: '11px', fontWeight: '700', flexShrink: 0,
                    }}>
                      {idx + 1}
                    </div>
                    <input
                      value={q.text}
                      onChange={e => updateQuestion(idx, 'text', e.target.value)}
                      placeholder={`Question ${idx + 1}... Ex: Quelle est ta ville ?`}
                      style={{
                        flex: 1, padding: '8px 12px',
                        background: 'rgba(255,255,255,0.04)',
                        border: '1px solid rgba(255,255,255,0.08)',
                        borderRadius: '8px', color: '#fff', fontSize: '13px', outline: 'none',
                      }}
                      onFocus={e => e.target.style.borderColor = 'rgba(217,28,210,0.3)'}
                      onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.08)'}
                    />
                    <button
                      onClick={() => removeQuestion(idx)}
                      style={{
                        background: 'none', border: 'none',
                        color: 'rgba(239,68,68,0.6)', cursor: 'pointer', padding: '4px',
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>

                  {/* Type selector */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: q.type === 'buttons' ? '12px' : '0' }}>
                    {QUESTION_TYPES.map(qt => (
                      <button
                        key={qt.value}
                        onClick={() => updateQuestion(idx, 'type', qt.value)}
                        style={{
                          padding: '4px 10px', borderRadius: '14px',
                          background: q.type === qt.value ? 'rgba(217,28,210,0.15)' : 'transparent',
                          border: q.type === qt.value
                            ? '1px solid rgba(217,28,210,0.3)'
                            : '1px solid rgba(255,255,255,0.06)',
                          color: q.type === qt.value ? '#D91CD2' : 'rgba(255,255,255,0.35)',
                          fontSize: '10px', fontWeight: '600', cursor: 'pointer',
                          display: 'flex', alignItems: 'center', gap: '4px',
                          transition: 'all 0.15s',
                        }}
                      >
                        <span style={{ fontSize: '10px' }}>{qt.icon}</span> {qt.label}
                      </button>
                    ))}
                  </div>

                  {/* Options for buttons type */}
                  {q.type === 'buttons' && (
                    <div style={{ marginTop: '8px', paddingLeft: '34px' }}>
                      {(q.options || []).map((opt, oIdx) => (
                        <div key={oIdx} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                          <span style={{ color: 'rgba(217,28,210,0.5)', fontSize: '10px' }}>●</span>
                          <input
                            value={opt}
                            onChange={e => updateOption(idx, oIdx, e.target.value)}
                            placeholder={`Option ${oIdx + 1}`}
                            style={{
                              flex: 1, padding: '6px 10px',
                              background: 'rgba(255,255,255,0.04)',
                              border: '1px solid rgba(255,255,255,0.06)',
                              borderRadius: '6px', color: '#fff', fontSize: '12px', outline: 'none',
                            }}
                          />
                          <button
                            onClick={() => removeOption(idx, oIdx)}
                            style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.2)', cursor: 'pointer', padding: '2px' }}
                          >
                            <X size={12} />
                          </button>
                        </div>
                      ))}
                      <button
                        onClick={() => addOption(idx)}
                        style={{
                          background: 'none', border: '1px dashed rgba(217,28,210,0.2)',
                          borderRadius: '6px', color: 'rgba(217,28,210,0.5)',
                          fontSize: '11px', padding: '4px 12px', cursor: 'pointer',
                          marginTop: '4px',
                        }}
                      >
                        + Option
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* ====== STEP 3: Actions de fin ====== */}
          {step === 3 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <p style={{ color: '#fff', fontSize: '14px', fontWeight: '600', margin: '0 0 4px' }}>
                  Actions après le tunnel
                </p>
                <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px', margin: 0 }}>
                  L'IA proposera ces actions une fois les questions terminées.
                </p>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {ACTION_TYPES.map(action => {
                  const isActive = (linkData.end_actions || []).find(a => a.type === action.value);
                  return (
                    <button
                      key={action.value}
                      onClick={() => toggleAction(action.value)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: '14px',
                        padding: '14px 16px', borderRadius: '12px',
                        background: isActive ? `${action.color}11` : 'rgba(255,255,255,0.02)',
                        border: isActive ? `1px solid ${action.color}44` : '1px solid rgba(255,255,255,0.06)',
                        color: isActive ? action.color : 'rgba(255,255,255,0.5)',
                        cursor: 'pointer', textAlign: 'left', width: '100%',
                        transition: 'all 0.2s',
                      }}
                    >
                      <div style={{
                        width: '36px', height: '36px', borderRadius: '10px',
                        background: isActive ? `${action.color}22` : 'rgba(255,255,255,0.04)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        transition: 'all 0.2s',
                      }}>
                        {action.icon}
                      </div>
                      <div style={{ flex: 1 }}>
                        <span style={{ fontSize: '13px', fontWeight: '600' }}>{action.label}</span>
                      </div>
                      <div style={{
                        width: '20px', height: '20px', borderRadius: '4px',
                        border: isActive ? `2px solid ${action.color}` : '2px solid rgba(255,255,255,0.15)',
                        background: isActive ? action.color : 'transparent',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        transition: 'all 0.2s',
                      }}>
                        {isActive && <Check size={12} color="#fff" />}
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Résumé */}
              <div style={{
                background: 'rgba(217,28,210,0.06)',
                border: '1px solid rgba(217,28,210,0.15)',
                borderRadius: '12px', padding: '16px',
              }}>
                <p style={{ color: '#D91CD2', fontSize: '12px', fontWeight: '700', margin: '0 0 10px' }}>
                  📋 Résumé du lien
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px' }}>Nom</span>
                    <span style={{ color: '#fff', fontSize: '11px', fontWeight: '600' }}>{linkData.title || '—'}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px' }}>Type de lead</span>
                    <span style={{ color: '#fff', fontSize: '11px', fontWeight: '600' }}>
                      {LEAD_TYPES.find(l => l.value === linkData.lead_type)?.label || '—'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px' }}>Questions</span>
                    <span style={{ color: '#fff', fontSize: '11px', fontWeight: '600' }}>
                      {linkData.tunnel_questions.length} étape{linkData.tunnel_questions.length > 1 ? 's' : ''}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px' }}>Actions</span>
                    <span style={{ color: '#fff', fontSize: '11px', fontWeight: '600' }}>
                      {(linkData.end_actions || []).length} action{(linkData.end_actions || []).length > 1 ? 's' : ''}
                    </span>
                  </div>
                  {linkData.custom_prompt && (
                    <div style={{ marginTop: '6px', paddingTop: '6px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                      <span style={{ color: 'rgba(139,92,246,0.6)', fontSize: '10px' }}>
                        ✦ Prompt IA: {linkData.custom_prompt.substring(0, 80)}…
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer navigation */}
        <div style={{
          padding: '16px 20px',
          borderTop: '1px solid rgba(255,255,255,0.06)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <button
            onClick={() => step > 1 ? setStep(step - 1) : onClose()}
            style={{
              padding: '10px 20px', borderRadius: '10px',
              background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.1)',
              color: 'rgba(255,255,255,0.6)', fontSize: '13px', fontWeight: '500',
              cursor: 'pointer',
            }}
          >
            {step > 1 ? '← Retour' : 'Annuler'}
          </button>

          {step < 3 ? (
            <button
              onClick={() => canGoNext() && setStep(step + 1)}
              disabled={!canGoNext()}
              style={{
                padding: '10px 24px', borderRadius: '10px',
                background: canGoNext()
                  ? 'linear-gradient(135deg, #D91CD2, #9333ea)'
                  : 'rgba(217,28,210,0.15)',
                border: 'none', color: '#fff', fontSize: '13px', fontWeight: '600',
                cursor: canGoNext() ? 'pointer' : 'not-allowed',
                opacity: canGoNext() ? 1 : 0.5,
                boxShadow: 'none', transition: 'all 0.2s',
              }}
              onMouseEnter={e => { if (canGoNext()) e.target.style.boxShadow = GLOW.violet; }}
              onMouseLeave={e => e.target.style.boxShadow = 'none'}
            >
              Suivant →
            </button>
          ) : (
            <button
              onClick={handleSave}
              disabled={saving || !linkData.title.trim()}
              style={{
                padding: '10px 24px', borderRadius: '10px',
                background: saving ? 'rgba(34,197,94,0.3)' : 'linear-gradient(135deg, #22c55e, #16a34a)',
                border: 'none', color: '#fff', fontSize: '13px', fontWeight: '700',
                cursor: saving ? 'wait' : 'pointer',
                opacity: saving ? 0.5 : 1,
                display: 'flex', alignItems: 'center', gap: '8px',
              }}
            >
              {saving ? '⏳ Création…' : editingLink ? '💾 Enregistrer' : '🚀 Créer le lien'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
});
SmartLinkModal.displayName = 'SmartLinkModal';

// SmartLinkCard est maintenant importé depuis ./SmartLinkCard.js (v98.1)

// ====== COMPOSANT PRINCIPAL ======
const SmartLinksSection = ({
  chatLinks = [],
  copiedLinkId,
  copyLinkToClipboard,
  deleteChatLink,
  updateChatLink,
  generateShareableLink,
  loadingConversations,
  API,
  coachEmail,
}) => {
  const [showModal, setShowModal] = useState(false);
  const [editingLink, setEditingLink] = useState(null);
  const [filter, setFilter] = useState('all');
  const [selectedLinks, setSelectedLinks] = useState(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [simulatorLink, setSimulatorLink] = useState(null);

  // Multi-sélection
  const getLinkId = (link) => link.id || link._id || link.link_token || '';
  const toggleSelect = useCallback((linkId) => {
    setSelectedLinks(prev => {
      const next = new Set(prev);
      if (next.has(linkId)) next.delete(linkId); else next.add(linkId);
      return next;
    });
  }, []);
  // selectAll is defined after filteredLinks below
  const handleBulkDelete = useCallback(async () => {
    if (selectedLinks.size === 0) return;
    setBulkDeleting(true);
    const ids = Array.from(selectedLinks);
    for (const id of ids) {
      try { await deleteChatLink(id); } catch (e) { console.error('Bulk delete error:', e); }
    }
    setSelectedLinks(new Set());
    setBulkDeleting(false);
  }, [selectedLinks, deleteChatLink]);

  const handleCreateOrUpdate = async (linkData, existingId) => {
    if (existingId) {
      // Mise à jour
      await updateChatLink(existingId, {
        title: linkData.title,
        custom_prompt: linkData.custom_prompt || null,
        lead_type: linkData.lead_type,
        tunnel_questions: linkData.tunnel_questions,
        end_actions: linkData.end_actions,
        welcome_message: linkData.welcome_message,
      });
    } else {
      // Création — on utilise generateShareableLink modifié pour supporter les données étendues
      // Pour l'instant, on crée via le endpoint existant + on update avec les champs supplémentaires
      await generateShareableLink(linkData.title, linkData.custom_prompt, {
        lead_type: linkData.lead_type,
        tunnel_questions: linkData.tunnel_questions,
        end_actions: linkData.end_actions,
        welcome_message: linkData.welcome_message,
      });
    }
    setShowModal(false);
    setEditingLink(null);
  };

  const handleEdit = (link) => {
    setEditingLink(link);
    setShowModal(true);
  };

  const handleDuplicate = async (link) => {
    await handleCreateOrUpdate({
      title: `${link.title} (copie)`,
      custom_prompt: link.custom_prompt || '',
      lead_type: link.lead_type || 'participant',
      tunnel_questions: link.tunnel_questions || [],
      end_actions: link.end_actions || [],
      welcome_message: link.welcome_message || '',
    });
  };

  // Filtrage
  const filteredLinks = filter === 'all'
    ? chatLinks
    : chatLinks.filter(l => (l.lead_type || 'participant') === filter);

  const allFilteredIds = filteredLinks.map(getLinkId);
  const allSelected = allFilteredIds.length > 0 && allFilteredIds.every(id => selectedLinks.has(id));
  const selectAll = () => {
    if (allSelected) setSelectedLinks(new Set());
    else setSelectedLinks(new Set(allFilteredIds));
  };

  // Stats
  const totalClicks = chatLinks.reduce((acc, l) => acc + (l.participant_count || 0), 0);

  return (
    <>
      {/* Header section */}
      <div style={{ padding: '20px', borderBottom: '1px solid rgba(217,28,210,0.1)' }}>
        {/* Titre + bouton créer */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{
              width: '36px', height: '36px', borderRadius: '10px',
              background: 'linear-gradient(135deg, #D91CD2, #9333ea)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 12px rgba(217,28,210,0.3)',
            }}>
              <Link2 size={18} color="#fff" />
            </div>
            <div>
              <h3 style={{ color: '#fff', fontSize: '16px', fontWeight: '700', margin: 0 }}>
                Liens Intelligents
              </h3>
              <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px', margin: '2px 0 0' }}>
                Créez des tunnels de conversion automatisés
              </p>
            </div>
          </div>

          <button
            onClick={() => { setEditingLink(null); setShowModal(true); }}
            style={{
              padding: '10px 20px', borderRadius: '24px',
              background: 'linear-gradient(135deg, #D91CD2, #9333ea)',
              border: 'none', color: '#fff', fontSize: '13px', fontWeight: '600',
              cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '8px',
              boxShadow: 'none', transition: 'all 0.25s',
            }}
            onMouseEnter={e => e.target.style.boxShadow = GLOW.violet}
            onMouseLeave={e => e.target.style.boxShadow = 'none'}
          >
            <Plus size={16} /> Créer un Lien Intelligent
          </button>
        </div>

        {/* Stats mini */}
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
          {[
            { label: 'Total liens', value: chatLinks.length, color: '#D91CD2' },
            { label: 'Total clics', value: totalClicks, color: '#22c55e' },
            { label: 'Avec tunnel', value: chatLinks.filter(l => (l.tunnel_questions || []).length > 0).length, color: '#f59e0b' },
          ].map((stat, i) => (
            <div key={i} style={{
              padding: '8px 14px', borderRadius: '10px',
              background: `${stat.color}08`,
              border: `1px solid ${stat.color}20`,
              display: 'flex', alignItems: 'center', gap: '8px',
            }}>
              <span style={{ color: stat.color, fontSize: '16px', fontWeight: '700' }}>{stat.value}</span>
              <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px' }}>{stat.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Filters */}
      {chatLinks.length > 0 && (
        <div style={{ padding: '12px 20px', display: 'flex', gap: '6px', flexWrap: 'wrap', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
          <button
            onClick={() => setFilter('all')}
            style={{
              padding: '4px 12px', borderRadius: '14px',
              background: filter === 'all' ? 'rgba(217,28,210,0.15)' : 'transparent',
              border: filter === 'all' ? '1px solid rgba(217,28,210,0.3)' : '1px solid rgba(255,255,255,0.06)',
              color: filter === 'all' ? '#D91CD2' : 'rgba(255,255,255,0.35)',
              fontSize: '11px', fontWeight: '600', cursor: 'pointer',
            }}
          >
            Tous ({chatLinks.length})
          </button>
          {LEAD_TYPES.map(lt => {
            const count = chatLinks.filter(l => (l.lead_type || 'participant') === lt.value).length;
            if (count === 0) return null;
            return (
              <button
                key={lt.value}
                onClick={() => setFilter(lt.value)}
                style={{
                  padding: '4px 12px', borderRadius: '14px',
                  background: filter === lt.value ? `${lt.color}18` : 'transparent',
                  border: filter === lt.value ? `1px solid ${lt.color}44` : '1px solid rgba(255,255,255,0.06)',
                  color: filter === lt.value ? lt.color : 'rgba(255,255,255,0.35)',
                  fontSize: '11px', fontWeight: '600', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: '4px',
                }}
              >
                {lt.icon} {lt.label} ({count})
              </button>
            );
          })}
        </div>
      )}

      {/* Barre multi-sélection + bulk delete */}
      {filteredLinks.length > 0 && (
        <div style={{
          padding: '10px 20px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          borderBottom: '1px solid rgba(255,255,255,0.04)',
          background: selectedLinks.size > 0 ? 'rgba(217,28,210,0.04)' : 'transparent',
          transition: 'background 0.2s',
        }}>
          <button
            onClick={selectAll}
            style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              background: 'none', border: 'none',
              color: allSelected ? '#D91CD2' : 'rgba(255,255,255,0.4)',
              fontSize: '12px', fontWeight: '600', cursor: 'pointer',
              padding: '4px 0',
            }}
          >
            {allSelected ? <CheckSquare size={16} /> : <Square size={16} />}
            {allSelected ? 'Tout désélectionner' : 'Tout sélectionner'}
          </button>
          {selectedLinks.size > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span style={{ color: '#D91CD2', fontSize: '12px', fontWeight: '600' }}>
                {selectedLinks.size} sélectionné{selectedLinks.size > 1 ? 's' : ''}
              </span>
              <button
                onClick={handleBulkDelete}
                disabled={bulkDeleting}
                style={{
                  padding: '7px 16px', borderRadius: '10px',
                  background: bulkDeleting ? 'rgba(239,68,68,0.15)' : 'rgba(239,68,68,0.12)',
                  border: '1px solid rgba(239,68,68,0.3)',
                  color: '#ef4444', fontSize: '12px', fontWeight: '700',
                  cursor: bulkDeleting ? 'wait' : 'pointer',
                  display: 'flex', alignItems: 'center', gap: '6px',
                  transition: 'all 0.2s',
                }}
                onMouseEnter={e => { if (!bulkDeleting) { e.currentTarget.style.background = 'rgba(239,68,68,0.22)'; e.currentTarget.style.boxShadow = '0 0 12px rgba(239,68,68,0.2)'; }}}
                onMouseLeave={e => { e.currentTarget.style.background = 'rgba(239,68,68,0.12)'; e.currentTarget.style.boxShadow = 'none'; }}
              >
                <Trash2 size={14} />
                {bulkDeleting ? 'Suppression...' : 'Supprimer la sélection'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* V143: Links grid — responsive, scrollable with max-height */}
      <div style={{ padding: '16px 20px', maxHeight: '500px', overflowY: 'auto' }}>
        {filteredLinks.length === 0 && (
          <div style={{
            textAlign: 'center', padding: '48px 20px',
            background: 'rgba(217,28,210,0.02)',
            border: '2px dashed rgba(217,28,210,0.12)',
            borderRadius: '16px',
          }}>
            <div style={{
              width: '56px', height: '56px', borderRadius: '16px',
              background: 'linear-gradient(135deg, rgba(217,28,210,0.1), rgba(147,51,234,0.08))',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 16px', fontSize: '24px',
            }}>
              🔗
            </div>
            <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '14px', margin: '0 0 4px', fontWeight: '600' }}>
              {filter !== 'all' ? 'Aucun lien de ce type' : 'Aucun lien créé'}
            </p>
            <p style={{ color: 'rgba(255,255,255,0.25)', fontSize: '12px', margin: 0 }}>
              Créez votre premier lien intelligent pour convertir vos prospects
            </p>
          </div>
        )}

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 340px), 1fr))',
          gap: '14px',
        }}>
          {filteredLinks.map(link => {
            const lid = getLinkId(link);
            return (
              <SmartLinkCard
                key={lid || Math.random()}
                link={link}
                copiedLinkId={copiedLinkId}
                onCopy={copyLinkToClipboard}
                onDelete={deleteChatLink}
                onEdit={handleEdit}
                onPreview={() => setSimulatorLink(link)}
                selected={selectedLinks.has(lid)}
                onToggleSelect={toggleSelect}
              />
            );
          })}
        </div>
      </div>

      {/* Simulateur d'aperçu */}
      <LinkSimulator
        link={simulatorLink}
        isOpen={!!simulatorLink}
        onClose={() => setSimulatorLink(null)}
      />

      {/* Modal */}
      <SmartLinkModal
        isOpen={showModal}
        onClose={() => { setShowModal(false); setEditingLink(null); }}
        onSave={handleCreateOrUpdate}
        editingLink={editingLink}
        API={API}
        coachEmail={coachEmail}
      />
    </>
  );
};

export default SmartLinksSection;

/**
 * CampaignModal.js - v12: Tunnel de création simplifié en 3 étapes
 * Étape 1: Médias & Objectif (prompt système, objectif IA, message, média)
 * Étape 2: Contacts & Canaux (destinataires, canaux)
 * Étape 3: Confirmation & Coût (récapitulatif, programmation, coût crédits)
 */
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { parseMediaUrl } from '../../services/MediaParser';

const STEPS = [
  { id: 1, label: 'Médias & Objectif', icon: '🎯' },
  { id: 2, label: 'Contacts & Canaux', icon: '👥' },
  { id: 3, label: 'Confirmation', icon: '✅' }
];

export default function CampaignModal({
  isOpen,
  onClose,
  // Campaign state
  newCampaign,
  setNewCampaign,
  editingCampaignId,
  // Contacts
  selectedRecipients,
  setSelectedRecipients,
  activeConversations,
  showConversationDropdown,
  setShowConversationDropdown,
  conversationSearch,
  setConversationSearch,
  // Media
  mediaLinks = [],
  resolvedThumbnail,
  // AI
  aiConfig,
  API,
  // Credits
  isSuperAdmin = false,
  campaignCreditCost = 1,
  coachCredits = null,
  // Handlers
  createCampaign,
  cancelEditCampaign,
  showCampaignToast,
  addScheduleSlot,
  removeScheduleSlot,
  updateScheduleSlot,
  // Pre-selected date from calendar
  preSelectedDate
}) {
  const [step, setStep] = useState(1);
  const [aiSuggestions, setAiSuggestions] = useState([]);
  const [aiSuggestionsLoading, setAiSuggestionsLoading] = useState(false);

  // Reset step when modal opens
  useEffect(() => {
    if (isOpen) setStep(1);
  }, [isOpen]);

  // Pre-fill date from calendar
  useEffect(() => {
    if (preSelectedDate && isOpen) {
      setNewCampaign(prev => ({
        ...prev,
        scheduleSlots: [{ date: preSelectedDate, time: '10:00' }]
      }));
    }
  }, [preSelectedDate, isOpen, setNewCampaign]);

  if (!isOpen) return null;

  const generateAiSuggestions = async () => {
    const descPrompt = (newCampaign.descriptionPrompt || '').trim();
    const sysPrompt = (newCampaign.systemPrompt || '').trim();
    if (!descPrompt && !sysPrompt) {
      showCampaignToast?.('⚠️ Remplissez un objectif d\'abord', 'error');
      return;
    }
    setAiSuggestionsLoading(true);
    try {
      const res = await axios.post(`${API}/ai/campaign-suggestions`, {
        campaign_goal: descPrompt,
        campaign_name: newCampaign.name || 'Campagne',
        recipient_count: selectedRecipients?.length || 1,
        system_prompt: sysPrompt,
        description_prompt: descPrompt
      });
      if (res.data.suggestions?.length > 0) {
        setAiSuggestions(res.data.suggestions);
        showCampaignToast?.('✨ 3 suggestions générées!', 'success');
      }
    } catch (err) {
      setAiSuggestions([
        { type: 'Promo', text: `🔥 Salut {prénom}! ${descPrompt || 'Offre spéciale'}! Réserve maintenant.` },
        { type: 'Relance', text: `👋 Hey {prénom}! ${descPrompt || 'On t\'attend'}!` },
        { type: 'Info', text: `📢 {prénom}, ${descPrompt || 'Nouvelle info'}! À bientôt.` }
      ]);
    } finally {
      setAiSuggestionsLoading(false);
    }
  };

  const canGoNext = () => {
    if (step === 1) return newCampaign.name?.trim() && newCampaign.message?.trim();
    if (step === 2) return selectedRecipients?.length > 0 || newCampaign.channels?.whatsapp || newCampaign.channels?.email || newCampaign.channels?.group;
    return true;
  };

  // YouTube detection for preview
  const ytMatch = (newCampaign.mediaUrl || '').match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})/);

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.8)', zIndex: 9999,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: '16px'
    }} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{
        background: 'linear-gradient(135deg, #1a1025 0%, #0d0a14 100%)',
        borderRadius: '16px', width: '100%', maxWidth: '600px',
        maxHeight: '90vh', overflow: 'hidden',
        border: '1px solid rgba(139, 92, 246, 0.3)',
        display: 'flex', flexDirection: 'column'
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 20px', borderBottom: '1px solid rgba(139, 92, 246, 0.2)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between'
        }}>
          <h3 style={{ color: '#fff', fontSize: '16px', fontWeight: 600, margin: 0 }}>
            {editingCampaignId ? '✏️ Modifier la campagne' : '📢 Nouvelle campagne'}
          </h3>
          <button onClick={onClose} style={{
            background: 'rgba(255,255,255,0.1)', border: 'none', color: '#fff',
            width: '32px', height: '32px', borderRadius: '8px', cursor: 'pointer', fontSize: '16px'
          }}>✕</button>
        </div>

        {/* Step Indicator */}
        <div style={{ padding: '12px 20px', display: 'flex', gap: '8px' }}>
          {STEPS.map(s => (
            <div key={s.id} onClick={() => { if (s.id < step || canGoNext()) setStep(s.id); }}
              style={{
                flex: 1, padding: '8px', borderRadius: '8px', textAlign: 'center', cursor: 'pointer',
                background: step === s.id ? 'rgba(139, 92, 246, 0.3)' : step > s.id ? 'rgba(34, 197, 94, 0.15)' : 'rgba(255,255,255,0.05)',
                border: step === s.id ? '1px solid rgba(139, 92, 246, 0.5)' : '1px solid transparent',
                transition: 'all 0.2s'
              }}>
              <div style={{ fontSize: '14px' }}>{s.icon}</div>
              <div style={{ fontSize: '10px', color: step >= s.id ? '#c4b5fd' : 'rgba(255,255,255,0.3)', marginTop: '2px' }}>{s.label}</div>
            </div>
          ))}
        </div>

        {/* Step Content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>

          {/* ===== ÉTAPE 1: Médias & Objectif ===== */}
          {step === 1 && (
            <div>
              {/* Nom */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', color: '#fff', fontSize: '13px', fontWeight: 500, marginBottom: '6px' }}>Nom de la campagne *</label>
                <input
                  value={newCampaign.name || ''}
                  onChange={e => setNewCampaign(prev => ({ ...prev, name: e.target.value }))}
                  placeholder="Ex: Promo Weekend Afrobeat"
                  style={{ width: '100%', padding: '10px 14px', borderRadius: '8px', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(139,92,246,0.3)', color: '#fff', fontSize: '14px', outline: 'none', boxSizing: 'border-box' }}
                />
              </div>

              {/* Prompt Système */}
              <div style={{ marginBottom: '16px', padding: '12px', borderRadius: '10px', background: 'rgba(139,92,246,0.08)', border: '1px solid rgba(139,92,246,0.2)' }}>
                <label style={{ display: 'block', color: '#c4b5fd', fontSize: '12px', fontWeight: 500, marginBottom: '6px' }}>🧠 Prompt Système <span style={{ color: 'rgba(255,255,255,0.4)' }}>(optionnel)</span></label>
                <textarea
                  value={newCampaign.systemPrompt || ''}
                  onChange={e => setNewCampaign(prev => ({ ...prev, systemPrompt: e.target.value }))}
                  rows={2}
                  placeholder="Ex: Tu es un coach Afrobeat motivant. Ton jeune et dynamique."
                  style={{ width: '100%', padding: '10px', borderRadius: '8px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', fontSize: '13px', resize: 'vertical', outline: 'none', boxSizing: 'border-box' }}
                />
              </div>

              {/* Objectif IA */}
              <div style={{ marginBottom: '16px', padding: '12px', borderRadius: '10px', background: 'rgba(234,179,8,0.08)', border: '1px solid rgba(234,179,8,0.2)' }}>
                <label style={{ display: 'block', color: '#fbbf24', fontSize: '12px', fontWeight: 500, marginBottom: '6px' }}>🎯 Objectif <span style={{ color: 'rgba(255,255,255,0.4)' }}>(pour l'IA)</span></label>
                <textarea
                  value={newCampaign.descriptionPrompt || ''}
                  onChange={e => setNewCampaign(prev => ({ ...prev, descriptionPrompt: e.target.value }))}
                  rows={2}
                  placeholder="Ex: Promouvoir le cours de dimanche avec -20%"
                  style={{ width: '100%', padding: '10px', borderRadius: '8px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', fontSize: '13px', resize: 'vertical', outline: 'none', boxSizing: 'border-box' }}
                />
              </div>

              {/* Message final + IA */}
              <div style={{ marginBottom: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <label style={{ color: '#fff', fontSize: '13px', fontWeight: 500 }}>📝 Message final *</label>
                  <button type="button" onClick={generateAiSuggestions} disabled={aiSuggestionsLoading}
                    style={{
                      padding: '5px 12px', borderRadius: '6px', border: 'none', fontSize: '11px', fontWeight: 600, cursor: 'pointer',
                      background: aiSuggestionsLoading ? 'rgba(139,92,246,0.2)' : 'linear-gradient(135deg, #9333ea, #6366f1)', color: '#fff'
                    }}>
                    {aiSuggestionsLoading ? '⏳ ...' : '🤖 Suggérer IA'}
                  </button>
                </div>
                <textarea
                  required
                  value={newCampaign.message || ''}
                  onChange={e => setNewCampaign(prev => ({ ...prev, message: e.target.value }))}
                  rows={4}
                  placeholder="Salut {prénom} ! 🎉 Profite de notre offre spéciale..."
                  style={{ width: '100%', padding: '10px', borderRadius: '8px', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(139,92,246,0.3)', color: '#fff', fontSize: '14px', resize: 'vertical', outline: 'none', boxSizing: 'border-box' }}
                />
                <p style={{ fontSize: '11px', color: 'rgba(255,255,255,0.4)', marginTop: '4px' }}>Variables: {'{prénom}'} sera remplacé par le nom du contact</p>
              </div>

              {/* AI Suggestions */}
              {aiSuggestions.length > 0 && (
                <div style={{ marginBottom: '16px' }}>
                  <p style={{ fontSize: '12px', color: '#c4b5fd', marginBottom: '8px' }}>💡 Suggestions IA — cliquez pour utiliser :</p>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {aiSuggestions.map((s, i) => (
                      <button key={i} type="button"
                        onClick={() => { setNewCampaign(prev => ({ ...prev, message: s.text })); setAiSuggestions([]); showCampaignToast?.('✅ Message inséré', 'success'); }}
                        style={{
                          padding: '10px 12px', borderRadius: '8px', textAlign: 'left', cursor: 'pointer',
                          background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(139,92,246,0.2)',
                          color: '#fff', fontSize: '12px', lineHeight: 1.4
                        }}>
                        <span style={{ color: '#a78bfa', fontWeight: 600 }}>{s.type}</span> — {s.text}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Média URL */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', color: '#fff', fontSize: '13px', fontWeight: 500, marginBottom: '6px' }}>📎 Média <span style={{ color: 'rgba(255,255,255,0.4)' }}>(optionnel)</span></label>
                {/* Quick select from saved media */}
                {mediaLinks?.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '8px' }}>
                    {mediaLinks.slice(0, 4).map(m => (
                      <button key={m.id} type="button"
                        onClick={() => setNewCampaign(prev => ({ ...prev, mediaUrl: m.video_url || m.thumbnail }))}
                        style={{
                          padding: '6px 10px', borderRadius: '6px', fontSize: '11px', cursor: 'pointer',
                          background: newCampaign.mediaUrl === (m.video_url || m.thumbnail) ? 'rgba(139,92,246,0.4)' : 'rgba(255,255,255,0.08)',
                          border: newCampaign.mediaUrl === (m.video_url || m.thumbnail) ? '1px solid #9333ea' : '1px solid rgba(255,255,255,0.15)',
                          color: '#fff'
                        }}>
                        {m.title?.slice(0, 15) || 'Média'}
                      </button>
                    ))}
                  </div>
                )}
                <input
                  type="url"
                  value={newCampaign.mediaUrl || ''}
                  onChange={e => setNewCampaign(prev => ({ ...prev, mediaUrl: e.target.value }))}
                  placeholder="https://youtube.com/... ou URL image"
                  style={{ width: '100%', padding: '10px 14px', borderRadius: '8px', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(139,92,246,0.3)', color: '#fff', fontSize: '13px', outline: 'none', boxSizing: 'border-box' }}
                />
                {/* Preview */}
                {newCampaign.mediaUrl && (
                  <div style={{ marginTop: '8px', display: 'flex', justifyContent: 'center' }}>
                    <div style={{
                      width: newCampaign.mediaFormat === '9:16' ? '120px' : newCampaign.mediaFormat === '1:1' ? '150px' : '220px',
                      height: newCampaign.mediaFormat === '9:16' ? '213px' : newCampaign.mediaFormat === '1:1' ? '150px' : '124px',
                      background: '#000', borderRadius: '8px', overflow: 'hidden', border: '1px solid rgba(139,92,246,0.3)'
                    }}>
                      {ytMatch ? (
                        <iframe src={`https://www.youtube.com/embed/${ytMatch[1]}`} title="YT" allow="autoplay" allowFullScreen style={{ width: '100%', height: '100%', border: 'none' }} />
                      ) : (
                        <img src={newCampaign.mediaUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} onError={e => { e.target.style.display = 'none'; }} />
                      )}
                    </div>
                  </div>
                )}
                {/* Format radio */}
                <div style={{ display: 'flex', gap: '16px', marginTop: '8px' }}>
                  {['9:16', '1:1', '16:9'].map(fmt => (
                    <label key={fmt} style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#fff', fontSize: '12px', cursor: 'pointer' }}>
                      <input type="radio" name="fmt" checked={newCampaign.mediaFormat === fmt} onChange={() => setNewCampaign(prev => ({ ...prev, mediaFormat: fmt }))} />
                      {fmt === '9:16' ? 'Stories' : fmt === '1:1' ? 'Carré' : 'Post'}
                    </label>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ===== ÉTAPE 2: Contacts & Canaux ===== */}
          {step === 2 && (
            <div>
              {/* Destinataires (panier) */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', color: '#fff', fontSize: '13px', fontWeight: 500, marginBottom: '8px' }}>
                  🎯 Destinataires ({selectedRecipients?.length || 0})
                </label>
                {/* Selected tags */}
                {selectedRecipients?.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '10px', padding: '8px', borderRadius: '8px', background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)' }}>
                    {selectedRecipients.map(r => (
                      <span key={r.id} style={{
                        display: 'inline-flex', alignItems: 'center', gap: '4px',
                        padding: '4px 10px', borderRadius: '20px', fontSize: '12px',
                        background: r.type === 'group' ? 'rgba(139,92,246,0.3)' : 'rgba(59,130,246,0.3)',
                        color: '#fff', border: '1px solid rgba(255,255,255,0.15)'
                      }}>
                        {r.type === 'group' ? '👥' : '👤'} {r.name}
                        <button type="button" onClick={() => setSelectedRecipients(prev => prev.filter(x => x.id !== r.id))}
                          style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.5)', cursor: 'pointer', fontSize: '12px', padding: '0 2px' }}>✕</button>
                      </span>
                    ))}
                  </div>
                )}
                {/* Search dropdown */}
                <div style={{ position: 'relative' }}>
                  <input
                    placeholder="🔍 Rechercher un groupe ou contact..."
                    value={conversationSearch || ''}
                    onChange={e => { setConversationSearch(e.target.value); setShowConversationDropdown(true); }}
                    onFocus={() => setShowConversationDropdown(true)}
                    style={{ width: '100%', padding: '10px 14px', borderRadius: '8px', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(139,92,246,0.3)', color: '#fff', fontSize: '13px', outline: 'none', boxSizing: 'border-box' }}
                  />
                  {showConversationDropdown && activeConversations?.length > 0 && (
                    <div style={{
                      position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
                      maxHeight: '200px', overflowY: 'auto', marginTop: '4px',
                      background: '#1a1025', borderRadius: '8px', border: '1px solid rgba(139,92,246,0.3)'
                    }}>
                      {activeConversations
                        .filter(c => !conversationSearch || (c.name || '').toLowerCase().includes(conversationSearch.toLowerCase()))
                        .filter(c => !selectedRecipients?.some(r => r.id === c.conversation_id))
                        .slice(0, 10)
                        .map(c => (
                          <div key={c.conversation_id}
                            onClick={() => {
                              setSelectedRecipients(prev => [...prev, { id: c.conversation_id, name: c.name || 'Sans nom', type: c.type || 'user' }]);
                              setConversationSearch('');
                              setShowConversationDropdown(false);
                            }}
                            style={{ padding: '10px 14px', cursor: 'pointer', borderBottom: '1px solid rgba(255,255,255,0.05)', color: '#fff', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}
                            onMouseEnter={e => e.currentTarget.style.background = 'rgba(139,92,246,0.15)'}
                            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                            <span>{c.type === 'group' ? '👥' : '👤'}</span>
                            <span>{c.name || 'Sans nom'}</span>
                          </div>
                        ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Canaux */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', color: '#fff', fontSize: '13px', fontWeight: 500, marginBottom: '8px' }}>📡 Canaux d'envoi</label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {[
                    { key: 'internal', label: '💌 Chat Interne', color: '#22c55e' },
                    { key: 'whatsapp', label: '📱 WhatsApp', color: '#25d366' },
                    { key: 'email', label: '📧 Email', color: '#3b82f6' },
                    { key: 'group', label: '👥 Groupe', color: '#a855f7' }
                  ].map(ch => (
                    <button key={ch.key} type="button"
                      onClick={() => setNewCampaign(prev => ({ ...prev, channels: { ...prev.channels, [ch.key]: !prev.channels?.[ch.key] } }))}
                      style={{
                        padding: '8px 14px', borderRadius: '8px', fontSize: '12px', fontWeight: 500, cursor: 'pointer',
                        background: newCampaign.channels?.[ch.key] ? `${ch.color}30` : 'rgba(255,255,255,0.05)',
                        border: newCampaign.channels?.[ch.key] ? `1px solid ${ch.color}80` : '1px solid rgba(255,255,255,0.1)',
                        color: newCampaign.channels?.[ch.key] ? ch.color : 'rgba(255,255,255,0.5)'
                      }}>
                      {ch.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* CTA */}
              <div style={{ marginBottom: '16px', padding: '12px', borderRadius: '10px', background: 'rgba(139,92,246,0.06)', border: '1px solid rgba(139,92,246,0.15)' }}>
                <label style={{ display: 'block', color: '#c4b5fd', fontSize: '12px', fontWeight: 500, marginBottom: '8px' }}>🔘 Bouton d'action (CTA)</label>
                <select
                  value={newCampaign.ctaType || 'none'}
                  onChange={e => setNewCampaign(prev => ({ ...prev, ctaType: e.target.value, ctaText: '', ctaLink: '' }))}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', fontSize: '13px', outline: 'none' }}>
                  <option value="none">Aucun bouton</option>
                  <option value="reserver">🗓️ Réserver</option>
                  <option value="offre">🎁 Offre</option>
                  <option value="personnalise">✨ Personnalisé</option>
                </select>
                {newCampaign.ctaType && newCampaign.ctaType !== 'none' && (
                  <div style={{ marginTop: '8px', display: 'flex', gap: '8px' }}>
                    <input
                      value={newCampaign.ctaText || ''}
                      onChange={e => setNewCampaign(prev => ({ ...prev, ctaText: e.target.value }))}
                      placeholder="Texte du bouton"
                      style={{ flex: 1, padding: '8px 12px', borderRadius: '8px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', fontSize: '12px', outline: 'none' }}
                    />
                    {(newCampaign.ctaType === 'offre' || newCampaign.ctaType === 'personnalise') && (
                      <input
                        value={newCampaign.ctaLink || ''}
                        onChange={e => setNewCampaign(prev => ({ ...prev, ctaLink: e.target.value }))}
                        placeholder="https://..."
                        style={{ flex: 1, padding: '8px 12px', borderRadius: '8px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', fontSize: '12px', outline: 'none' }}
                      />
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ===== ÉTAPE 3: Confirmation ===== */}
          {step === 3 && (
            <div>
              {/* Recap */}
              <div style={{ marginBottom: '16px', padding: '16px', borderRadius: '10px', background: 'rgba(139,92,246,0.08)', border: '1px solid rgba(139,92,246,0.2)' }}>
                <h4 style={{ color: '#c4b5fd', fontSize: '13px', fontWeight: 600, marginBottom: '12px', marginTop: 0 }}>📋 Récapitulatif</h4>
                <div style={{ display: 'grid', gap: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                    <span style={{ color: 'rgba(255,255,255,0.5)' }}>Campagne</span>
                    <span style={{ color: '#fff', fontWeight: 500 }}>{newCampaign.name || '—'}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                    <span style={{ color: 'rgba(255,255,255,0.5)' }}>Destinataires</span>
                    <span style={{ color: '#fff', fontWeight: 500 }}>{selectedRecipients?.length || 0} contact(s)</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                    <span style={{ color: 'rgba(255,255,255,0.5)' }}>Canaux</span>
                    <span style={{ color: '#fff' }}>
                      {[newCampaign.channels?.internal && '💌', newCampaign.channels?.whatsapp && '📱', newCampaign.channels?.email && '📧', newCampaign.channels?.group && '👥'].filter(Boolean).join(' ') || '💌'}
                    </span>
                  </div>
                  {newCampaign.mediaUrl && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                      <span style={{ color: 'rgba(255,255,255,0.5)' }}>Média</span>
                      <span style={{ color: '#22c55e' }}>✓ Attaché</span>
                    </div>
                  )}
                  {newCampaign.systemPrompt && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                      <span style={{ color: 'rgba(255,255,255,0.5)' }}>Prompt IA</span>
                      <span style={{ color: '#a78bfa' }}>✓ Personnalisé</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Message preview */}
              <div style={{ marginBottom: '16px', padding: '12px', borderRadius: '10px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}>
                <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', marginBottom: '4px', marginTop: 0 }}>Message :</p>
                <p style={{ color: '#fff', fontSize: '13px', lineHeight: 1.5, margin: 0, whiteSpace: 'pre-wrap' }}>{newCampaign.message || '—'}</p>
              </div>

              {/* Programmation */}
              <div style={{ marginBottom: '16px', padding: '12px', borderRadius: '10px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <label style={{ color: '#fff', fontSize: '13px', fontWeight: 500 }}>⏰ Programmation</label>
                  <button type="button" onClick={() => addScheduleSlot?.()}
                    style={{ padding: '4px 10px', borderRadius: '6px', background: 'rgba(139,92,246,0.2)', border: '1px solid rgba(139,92,246,0.3)', color: '#c4b5fd', fontSize: '11px', cursor: 'pointer' }}>
                    + Date
                  </button>
                </div>
                {(newCampaign.scheduleSlots || []).length === 0 && (
                  <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px', margin: 0 }}>📤 Envoi immédiat à la création</p>
                )}
                {(newCampaign.scheduleSlots || []).map((slot, i) => (
                  <div key={i} style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '6px' }}>
                    <input type="date" value={slot.date || ''} onChange={e => updateScheduleSlot?.(i, 'date', e.target.value)}
                      style={{ flex: 1, padding: '6px 10px', borderRadius: '6px', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', fontSize: '12px' }} />
                    <input type="time" value={slot.time || ''} onChange={e => updateScheduleSlot?.(i, 'time', e.target.value)}
                      style={{ width: '90px', padding: '6px 10px', borderRadius: '6px', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', fontSize: '12px' }} />
                    <button type="button" onClick={() => removeScheduleSlot?.(i)}
                      style={{ padding: '4px 8px', borderRadius: '4px', background: 'rgba(239,68,68,0.2)', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: '12px' }}>✕</button>
                  </div>
                ))}
              </div>

              {/* Coût */}
              <div style={{ padding: '12px', borderRadius: '10px', background: 'rgba(139,92,246,0.1)', border: '1px solid rgba(139,92,246,0.3)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: '13px' }}>💰 Coût estimé</span>
                  {isSuperAdmin ? (
                    <span style={{ color: '#a78bfa', fontWeight: 700, fontSize: '14px' }}>∞ Illimité</span>
                  ) : (
                    <span style={{ color: '#fff', fontWeight: 700, fontSize: '14px' }}>
                      {(selectedRecipients?.length || 0) * campaignCreditCost} crédit{(selectedRecipients?.length || 0) * campaignCreditCost > 1 ? 's' : ''}
                    </span>
                  )}
                </div>
                {!isSuperAdmin && coachCredits !== null && coachCredits >= 0 && coachCredits < (selectedRecipients?.length || 0) * campaignCreditCost && (
                  <p style={{ color: '#ef4444', fontSize: '11px', marginTop: '4px', marginBottom: 0 }}>⚠️ Solde insuffisant ({coachCredits} crédits)</p>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer with navigation */}
        <div style={{
          padding: '12px 20px', borderTop: '1px solid rgba(139,92,246,0.2)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px'
        }}>
          {step > 1 ? (
            <button type="button" onClick={() => setStep(step - 1)}
              style={{ padding: '10px 20px', borderRadius: '8px', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', fontSize: '13px', cursor: 'pointer', fontWeight: 500 }}>
              ← Retour
            </button>
          ) : (
            <button type="button" onClick={onClose}
              style={{ padding: '10px 20px', borderRadius: '8px', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', fontSize: '13px', cursor: 'pointer', fontWeight: 500 }}>
              Annuler
            </button>
          )}

          {step < 3 ? (
            <button type="button" onClick={() => { if (canGoNext()) setStep(step + 1); }}
              disabled={!canGoNext()}
              style={{
                padding: '10px 24px', borderRadius: '8px', border: 'none', fontSize: '13px', fontWeight: 600, cursor: canGoNext() ? 'pointer' : 'not-allowed',
                background: canGoNext() ? 'linear-gradient(135deg, #9333ea, #6366f1)' : 'rgba(139,92,246,0.2)',
                color: '#fff', opacity: canGoNext() ? 1 : 0.5
              }}>
              Suivant →
            </button>
          ) : (
            <button type="button"
              onClick={(e) => { createCampaign(e); onClose(); }}
              style={{
                padding: '10px 24px', borderRadius: '8px', border: 'none', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
                background: 'linear-gradient(135deg, #22c55e, #16a34a)', color: '#fff'
              }}>
              {editingCampaignId ? '💾 Enregistrer' : `🚀 Créer (${selectedRecipients?.length || 0} dest.)`}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

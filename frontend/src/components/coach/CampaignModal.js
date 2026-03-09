/**
 * CampaignModal.js — v18: Tunnel de création en 3 étapes avec sélection contacts corrigée
 * Étape 1: Médias & Objectif (prompt système, objectif IA, message, média)
 * Étape 2: Contacts & Canaux (checkboxes multi-select, recherche, import, sync)
 * Étape 3: Confirmation & Coût (récapitulatif, programmation, coût crédits)
 *
 * v18 FIX: Sélection par checkboxes fonctionnelle, contacts unifiés (participants + users + groupes)
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { parseContacts } from '../../utils/contactParser';

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
  preSelectedDate,
  // v16.3: Chat links pour CTA "Lier à une Conversation"
  chatLinks = [],
  // v18: Coach email for unified contacts
  coachEmail
}) {
  const [step, setStep] = useState(1);
  const [aiSuggestions, setAiSuggestions] = useState([]);
  const [aiSuggestionsLoading, setAiSuggestionsLoading] = useState(false);
  // v87: Anti-doublon bouton Programmer/Créer
  const [isSubmitting, setIsSubmitting] = useState(false);

  // v18: Unified contacts system
  const [allContacts, setAllContacts] = useState([]);
  const [contactsLoading, setContactsLoading] = useState(false);
  const [contactSearch, setContactSearch] = useState('');
  const [contactFilter, setContactFilter] = useState('all'); // all, group, user

  // v17.3: Import contacts
  const importFileRef = useRef(null);
  const [importedContacts, setImportedContacts] = useState([]);
  const [showImportPreview, setShowImportPreview] = useState(false);

  // v18: Load unified contacts when step 2 opens
  const loadUnifiedContacts = useCallback(async () => {
    if (!API) return;
    setContactsLoading(true);
    try {
      const headers = { 'X-User-Email': coachEmail || '' };
      const res = await axios.get(`${API}/contacts/all`, { headers });
      if (res.data.success) {
        setAllContacts(res.data.contacts || []);
      }
    } catch (err) {
      // Fallback to activeConversations
      if (activeConversations?.length > 0) {
        setAllContacts(activeConversations.map(c => ({
          id: c.conversation_id,
          name: (c.name || 'Sans nom').replace(/^(👤|👥)\s*/, ''),
          type: c.type || 'user',
          email: c.email || null,
          phone: null,
          source: 'session',
          category: c.mode || 'user'
        })));
      }
    } finally {
      setContactsLoading(false);
    }
  }, [API, coachEmail, activeConversations]);

  useEffect(() => {
    if (isOpen && step === 2 && allContacts.length === 0) {
      loadUnifiedContacts();
    }
  }, [isOpen, step, loadUnifiedContacts, allContacts.length]);

  const handleFileImport = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      const text = evt.target.result;
      const contacts = parseContacts(text, file.name);
      setImportedContacts(contacts);
      setShowImportPreview(true);
    };
    reader.readAsText(file);
    e.target.value = ''; // reset input
  };

  const addImportedToRecipients = () => {
    const newRecipients = importedContacts
      .filter(c => c.phone || c.email)
      .map(c => ({
        id: `import_${c.phone || c.email}`,
        name: c.name || c.phone || c.email,
        type: 'user',
        phone: c.phone,
        email: c.email,
        imported: true
      }));
    // Deduplicate against existing
    const existingIds = new Set((selectedRecipients || []).map(r => r.id));
    const unique = newRecipients.filter(r => !existingIds.has(r.id));
    setSelectedRecipients(prev => [...prev, ...unique]);
    setShowImportPreview(false);
    setImportedContacts([]);
  };

  // v18: Toggle contact selection (checkbox)
  const toggleContact = (contact) => {
    const isSelected = selectedRecipients?.some(r => r.id === contact.id);
    if (isSelected) {
      setSelectedRecipients(prev => prev.filter(r => r.id !== contact.id));
    } else {
      setSelectedRecipients(prev => [...prev, {
        id: contact.id,
        name: contact.name || 'Sans nom',
        type: contact.type || 'user',
        phone: contact.phone || null,
        email: contact.email || null
      }]);
    }
  };

  // v18: Select all visible contacts
  const selectAllVisible = () => {
    const existingIds = new Set((selectedRecipients || []).map(r => r.id));
    const newOnes = filteredContacts
      .filter(c => !existingIds.has(c.id))
      .map(c => ({
        id: c.id,
        name: c.name || 'Sans nom',
        type: c.type || 'user',
        phone: c.phone || null,
        email: c.email || null
      }));
    setSelectedRecipients(prev => [...prev, ...newOnes]);
  };

  const deselectAll = () => {
    setSelectedRecipients([]);
  };

  // Filtered contacts for display
  const filteredContacts = allContacts.filter(c => {
    const matchSearch = !contactSearch ||
      (c.name || '').toLowerCase().includes(contactSearch.toLowerCase()) ||
      (c.email || '').toLowerCase().includes(contactSearch.toLowerCase()) ||
      (c.phone || '').includes(contactSearch);
    const matchFilter =
      contactFilter === 'all' ? true :
      contactFilter === 'group' ? c.type === 'group' :
      c.type === 'user';
    return matchSearch && matchFilter;
  });

  // v13: Calcul coût et blocage crédits
  const totalCost = (selectedRecipients?.length || 0) * campaignCreditCost;
  const insufficientCredits = !isSuperAdmin && coachCredits !== null && coachCredits !== -1 && coachCredits < Math.max(1, totalCost);
  const canCreate = isSuperAdmin || !insufficientCredits;

  // Reset step when modal opens
  useEffect(() => {
    if (isOpen) {
      setStep(1);
      setAllContacts([]);
    }
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
  const ytMatch = (newCampaign.mediaUrl || '').match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})/);

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
                        <div style={{ position: 'relative', width: '100%', height: '100%' }}>
                          <img src={`https://img.youtube.com/vi/${ytMatch[1]}/hqdefault.jpg`} alt="YT" style={{ width: '100%', height: '100%', objectFit: 'cover' }} onError={e => { e.target.src = `https://img.youtube.com/vi/${ytMatch[1]}/default.jpg`; }} />
                          <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', width: '40px', height: '40px', background: 'rgba(255,0,0,0.85)', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <div style={{ width: 0, height: 0, borderTop: '8px solid transparent', borderBottom: '8px solid transparent', borderLeft: '14px solid #fff', marginLeft: '2px' }} />
                          </div>
                        </div>
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

          {/* ===== ÉTAPE 2: Contacts & Canaux (v18: CHECKBOX MULTI-SELECT) ===== */}
          {step === 2 && (
            <div>
              {/* Destinataires header + counter */}
              <div style={{ marginBottom: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <label style={{ color: '#fff', fontSize: '13px', fontWeight: 500 }}>
                    🎯 Destinataires ({selectedRecipients?.length || 0} sélectionnés)
                  </label>
                  <div style={{ display: 'flex', gap: '6px' }}>
                    {selectedRecipients?.length > 0 && (
                      <button type="button" onClick={deselectAll} style={{
                        padding: '4px 10px', borderRadius: '6px', fontSize: '10px', fontWeight: 600,
                        background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)',
                        color: '#ef4444', cursor: 'pointer'
                      }}>Tout désélectionner</button>
                    )}
                    {filteredContacts.length > 0 && (
                      <button type="button" onClick={selectAllVisible} style={{
                        padding: '4px 10px', borderRadius: '6px', fontSize: '10px', fontWeight: 600,
                        background: 'rgba(34,197,94,0.15)', border: '1px solid rgba(34,197,94,0.3)',
                        color: '#22c55e', cursor: 'pointer'
                      }}>Tout sélectionner</button>
                    )}
                  </div>
                </div>

                {/* Selected tags (compact view) */}
                {selectedRecipients?.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginBottom: '10px', padding: '8px', borderRadius: '8px', background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)', maxHeight: '80px', overflowY: 'auto' }}>
                    {selectedRecipients.map(r => (
                      <span key={r.id} style={{
                        display: 'inline-flex', alignItems: 'center', gap: '3px',
                        padding: '3px 8px', borderRadius: '12px', fontSize: '11px',
                        background: r.type === 'group' ? 'rgba(139,92,246,0.25)' : 'rgba(59,130,246,0.25)',
                        color: '#fff', border: '1px solid rgba(255,255,255,0.1)'
                      }}>
                        {r.type === 'group' ? '👥' : '👤'} {(r.name || '').slice(0, 20)}
                        <button type="button" onClick={() => setSelectedRecipients(prev => prev.filter(x => x.id !== r.id))}
                          style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', cursor: 'pointer', fontSize: '10px', padding: '0 1px', lineHeight: 1 }}>✕</button>
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Search + Filter */}
              <div style={{ marginBottom: '10px' }}>
                <input
                  placeholder="🔍 Rechercher un contact, groupe, email, téléphone..."
                  value={contactSearch}
                  onChange={e => setContactSearch(e.target.value)}
                  style={{
                    width: '100%', padding: '10px 14px', borderRadius: '8px',
                    background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(139,92,246,0.3)',
                    color: '#fff', fontSize: '13px', outline: 'none', boxSizing: 'border-box', marginBottom: '6px'
                  }}
                />
                <div style={{ display: 'flex', gap: '6px' }}>
                  {[
                    { key: 'all', label: 'Tous', count: allContacts.length },
                    { key: 'group', label: '👥 Groupes', count: allContacts.filter(c => c.type === 'group').length },
                    { key: 'user', label: '👤 Contacts', count: allContacts.filter(c => c.type === 'user').length }
                  ].map(f => (
                    <button key={f.key} type="button" onClick={() => setContactFilter(f.key)} style={{
                      padding: '4px 10px', borderRadius: '14px', fontSize: '11px', fontWeight: 500, cursor: 'pointer',
                      background: contactFilter === f.key ? 'rgba(139,92,246,0.3)' : 'rgba(255,255,255,0.05)',
                      border: contactFilter === f.key ? '1px solid rgba(139,92,246,0.5)' : '1px solid rgba(255,255,255,0.08)',
                      color: contactFilter === f.key ? '#c4b5fd' : 'rgba(255,255,255,0.5)'
                    }}>
                      {f.label} ({f.count})
                    </button>
                  ))}
                </div>
              </div>

              {/* Contacts List with Checkboxes */}
              <div style={{
                maxHeight: '220px', overflowY: 'auto',
                borderRadius: '10px', border: '1px solid rgba(255,255,255,0.08)',
                marginBottom: '12px'
              }}>
                {contactsLoading ? (
                  <div style={{ padding: '20px', textAlign: 'center', color: 'rgba(255,255,255,0.4)', fontSize: '12px' }}>⏳ Chargement des contacts...</div>
                ) : filteredContacts.length === 0 ? (
                  <div style={{ padding: '20px', textAlign: 'center', color: 'rgba(255,255,255,0.4)', fontSize: '12px' }}>
                    {contactSearch ? 'Aucun résultat' : 'Aucun contact disponible'}
                  </div>
                ) : (
                  filteredContacts.slice(0, 100).map((c, i) => {
                    const isChecked = selectedRecipients?.some(r => r.id === c.id);
                    return (
                      <div key={c.id || i}
                        onClick={() => toggleContact(c)}
                        style={{
                          display: 'flex', alignItems: 'center', gap: '10px',
                          padding: '8px 12px', cursor: 'pointer',
                          borderBottom: '1px solid rgba(255,255,255,0.04)',
                          background: isChecked ? 'rgba(34,197,94,0.08)' : i % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent',
                          transition: 'background 0.15s'
                        }}
                        onMouseEnter={e => { if (!isChecked) e.currentTarget.style.background = 'rgba(139,92,246,0.08)'; }}
                        onMouseLeave={e => { if (!isChecked) e.currentTarget.style.background = i % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent'; }}
                      >
                        {/* Checkbox */}
                        <div style={{
                          width: '18px', height: '18px', borderRadius: '4px', flexShrink: 0,
                          border: isChecked ? '2px solid #22c55e' : '2px solid rgba(255,255,255,0.2)',
                          background: isChecked ? 'rgba(34,197,94,0.3)' : 'transparent',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          transition: 'all 0.15s'
                        }}>
                          {isChecked && <span style={{ color: '#22c55e', fontSize: '12px', fontWeight: 700 }}>✓</span>}
                        </div>
                        {/* Icon */}
                        <span style={{ fontSize: '14px', width: '20px', textAlign: 'center', flexShrink: 0 }}>
                          {c.type === 'group' ? '👥' : c.source === 'google' ? '🔵' : '👤'}
                        </span>
                        {/* Name + details */}
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: '12px', color: '#fff', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {c.name || 'Sans nom'}
                          </div>
                          <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.35)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {c.type === 'group' ? `${c.member_count || 0} membres` : [c.email, c.phone].filter(Boolean).join(' · ') || ''}
                          </div>
                        </div>
                        {/* Source badge */}
                        <span style={{
                          padding: '2px 6px', borderRadius: '8px', fontSize: '9px', flexShrink: 0,
                          background: c.type === 'group' ? 'rgba(139,92,246,0.15)' : c.source === 'google' ? 'rgba(34,197,94,0.12)' : 'rgba(255,255,255,0.05)',
                          color: c.type === 'group' ? '#a855f7' : c.source === 'google' ? '#22c55e' : 'rgba(255,255,255,0.4)'
                        }}>
                          {c.type === 'group' ? 'Groupe' : c.source === 'google' ? 'Google' : c.source === 'app' ? 'App' : 'CRM'}
                        </span>
                      </div>
                    );
                  })
                )}
                {filteredContacts.length > 100 && (
                  <div style={{ padding: '8px', textAlign: 'center', color: 'rgba(255,255,255,0.4)', fontSize: '11px' }}>
                    ... et {filteredContacts.length - 100} autres — affinez la recherche
                  </div>
                )}
              </div>

              {/* Import CSV/vCard */}
              <div style={{ marginBottom: '12px' }}>
                <input
                  ref={importFileRef}
                  type="file"
                  accept=".csv,.vcf,.txt"
                  onChange={handleFileImport}
                  style={{ display: 'none' }}
                />
                <button
                  type="button"
                  onClick={() => importFileRef.current?.click()}
                  style={{
                    width: '100%', padding: '10px', borderRadius: '8px', fontSize: '12px',
                    background: 'rgba(217,28,210,0.08)', border: '1px dashed rgba(217,28,210,0.4)',
                    color: '#D91CD2', cursor: 'pointer', fontWeight: 500
                  }}
                >
                  📤 Importer CSV / vCard (.vcf)
                </button>

                {/* Import Preview */}
                {showImportPreview && importedContacts.length > 0 && (
                  <div style={{
                    marginTop: '8px', padding: '10px', borderRadius: '8px',
                    background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.3)'
                  }}>
                    <p style={{ color: '#22c55e', fontSize: '12px', fontWeight: 600, margin: '0 0 6px 0' }}>
                      ✓ {importedContacts.length} contacts trouvés
                    </p>
                    <div style={{ maxHeight: '100px', overflowY: 'auto' }}>
                      {importedContacts.slice(0, 10).map((c, i) => (
                        <div key={i} style={{ fontSize: '11px', color: 'rgba(255,255,255,0.6)', padding: '2px 0' }}>
                          {c.name} {c.phone && `— ${c.phone}`} {c.email && `— ${c.email}`}
                        </div>
                      ))}
                      {importedContacts.length > 10 && (
                        <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.4)' }}>... et {importedContacts.length - 10} autres</div>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                      <button type="button" onClick={addImportedToRecipients}
                        style={{ flex: 1, padding: '8px', borderRadius: '6px', fontSize: '12px', fontWeight: 600, background: 'rgba(34,197,94,0.3)', border: '1px solid rgba(34,197,94,0.5)', color: '#22c55e', cursor: 'pointer' }}>
                        ✓ Ajouter tous
                      </button>
                      <button type="button" onClick={() => { setShowImportPreview(false); setImportedContacts([]); }}
                        style={{ padding: '8px 12px', borderRadius: '6px', fontSize: '12px', background: 'rgba(239,68,68,0.2)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444', cursor: 'pointer' }}>
                        ✕
                      </button>
                    </div>
                  </div>
                )}
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

              {/* CTA — v16.3 */}
              <div style={{ marginBottom: '16px', padding: '12px', borderRadius: '10px', background: 'rgba(139,92,246,0.06)', border: '1px solid rgba(139,92,246,0.15)' }}>
                <label style={{ display: 'block', color: '#c4b5fd', fontSize: '12px', fontWeight: 500, marginBottom: '8px' }}>🔘 Bouton d'action (CTA)</label>
                <select
                  value={newCampaign.ctaType || 'none'}
                  onChange={e => {
                    const val = e.target.value;
                    setNewCampaign(prev => ({ ...prev, ctaType: val, ctaText: val === 'conversation' ? 'Discuter avec l\'IA' : '', ctaLink: '' }));
                  }}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', fontSize: '13px', outline: 'none' }}>
                  <option value="none">Aucun bouton</option>
                  <option value="reserver">🗓️ Réserver</option>
                  <option value="offre">🎁 Offre</option>
                  <option value="conversation">💬 Lier à une Conversation</option>
                  <option value="personnalise">✨ Personnalisé</option>
                </select>

                {/* v16.3: Sélecteur de lien conversation */}
                {newCampaign.ctaType === 'conversation' && (
                  <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <select
                      value={newCampaign.ctaLink || ''}
                      onChange={e => {
                        const token = e.target.value;
                        const selectedLink = chatLinks.find(l => (l.link_token || l.token) === token);
                        const url = token ? `${window.location.origin}/?link=${token}` : '';
                        setNewCampaign(prev => ({
                          ...prev,
                          ctaLink: url,
                          ctaConversationToken: token,
                          ctaText: prev.ctaText || (selectedLink ? `💬 ${selectedLink.title || 'Discuter'}` : 'Discuter avec l\'IA')
                        }));
                      }}
                      style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', background: 'rgba(217,28,210,0.1)', border: '1px solid rgba(217,28,210,0.3)', color: '#fff', fontSize: '13px', outline: 'none' }}>
                      <option value="">— Choisir un lien de conversation —</option>
                      {chatLinks.map(link => {
                        const token = link.link_token || link.token || '';
                        return (
                          <option key={token} value={token}>
                            {link.title || 'Lien sans titre'} {link.custom_prompt || link.customPrompt ? '🤖' : ''}
                          </option>
                        );
                      })}
                    </select>
                    {chatLinks.length === 0 && (
                      <p style={{ color: '#f59e0b', fontSize: '11px', margin: 0 }}>
                        ⚠️ Créez d'abord un lien dans l'onglet Conversations.
                      </p>
                    )}
                    <input
                      value={newCampaign.ctaText || ''}
                      onChange={e => setNewCampaign(prev => ({ ...prev, ctaText: e.target.value }))}
                      placeholder="Texte du bouton (ex: Discuter avec l'IA)"
                      style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', fontSize: '12px', outline: 'none' }}
                    />
                    {newCampaign.ctaLink && (
                      <p style={{ color: 'rgba(217,28,210,0.6)', fontSize: '11px', margin: 0, wordBreak: 'break-all' }}>
                        🔗 {newCampaign.ctaLink}
                      </p>
                    )}
                  </div>
                )}

                {/* Types existants: texte + lien */}
                {newCampaign.ctaType && newCampaign.ctaType !== 'none' && newCampaign.ctaType !== 'conversation' && (
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

          {/* ===== ÉTAPE 3: Confirmation & Coût ===== */}
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

              {/* === COÛT & CRÉDITS === */}
              <div style={{
                padding: '16px', borderRadius: '12px',
                background: insufficientCredits ? 'rgba(239,68,68,0.08)' : 'rgba(139,92,246,0.1)',
                border: insufficientCredits ? '1px solid rgba(239,68,68,0.4)' : '1px solid rgba(139,92,246,0.3)'
              }}>
                {isSuperAdmin ? (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: '13px' }}>👑 Mode Super Admin</span>
                    <span style={{ color: '#D91CD2', fontWeight: 700, fontSize: '16px' }}>∞ Illimité</span>
                  </div>
                ) : (
                  <div>
                    <div style={{ display: 'grid', gap: '6px', marginBottom: '10px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                        <span style={{ color: 'rgba(255,255,255,0.5)' }}>Prix par envoi</span>
                        <span style={{ color: '#c4b5fd' }}>{campaignCreditCost} crédit{campaignCreditCost > 1 ? 's' : ''}</span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                        <span style={{ color: 'rgba(255,255,255,0.5)' }}>Nombre de destinataires</span>
                        <span style={{ color: '#c4b5fd' }}>× {selectedRecipients?.length || 0}</span>
                      </div>
                      <div style={{ height: '1px', background: 'rgba(255,255,255,0.1)', margin: '2px 0' }}></div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px', fontWeight: 600 }}>
                        <span style={{ color: '#fff' }}>Coût total</span>
                        <span style={{ color: insufficientCredits ? '#ef4444' : '#fff' }}>
                          {totalCost} crédit{totalCost > 1 ? 's' : ''}
                        </span>
                      </div>
                    </div>
                    <div style={{
                      padding: '10px 12px', borderRadius: '8px',
                      background: insufficientCredits ? 'rgba(239,68,68,0.12)' : 'rgba(34,197,94,0.08)',
                      border: insufficientCredits ? '1px solid rgba(239,68,68,0.3)' : '1px solid rgba(34,197,94,0.2)'
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: '12px', color: insufficientCredits ? '#ef4444' : 'rgba(255,255,255,0.6)' }}>
                          {insufficientCredits ? '🚫 Solde insuffisant' : '💰 Votre solde'}
                        </span>
                        <span style={{ fontSize: '13px', fontWeight: 700, color: insufficientCredits ? '#ef4444' : '#22c55e' }}>
                          {coachCredits ?? 0} crédit{(coachCredits ?? 0) !== 1 ? 's' : ''}
                        </span>
                      </div>
                      {insufficientCredits && (
                        <p style={{ color: '#fca5a5', fontSize: '11px', marginTop: '6px', marginBottom: 0, lineHeight: 1.4 }}>
                          Crédits insuffisants. Veuillez recharger votre pack pour programmer des campagnes.
                        </p>
                      )}
                    </div>
                  </div>
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
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
              <button type="button"
                disabled={!canCreate || isSubmitting}
                onClick={async (e) => {
                  if (canCreate && !isSubmitting) {
                    setIsSubmitting(true);
                    try { await createCampaign(e); } finally { setIsSubmitting(false); }
                    onClose();
                  }
                }}
                style={{
                  padding: '10px 24px', borderRadius: '8px', border: 'none', fontSize: '13px', fontWeight: 600,
                  cursor: (canCreate && !isSubmitting) ? 'pointer' : 'not-allowed',
                  background: isSubmitting ? 'rgba(107,114,128,0.5)' : canCreate ? 'linear-gradient(135deg, #22c55e, #16a34a)' : 'rgba(107,114,128,0.3)',
                  color: '#fff', opacity: (canCreate && !isSubmitting) ? 1 : 0.5
                }}>
                {isSubmitting ? '⏳ Envoi en cours...' : editingCampaignId ? '💾 Enregistrer' : canCreate ? `🚀 Créer (${selectedRecipients?.length || 0} dest.)` : '🔒 Crédits insuffisants'}
              </button>
              {!canCreate && (
                <span style={{ fontSize: '10px', color: '#ef4444' }}>Rechargez votre pack</span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

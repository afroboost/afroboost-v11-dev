// GroupChatModule.js — v155: Groupes de chat — CRUD complet + Edition + Ajout membres
// V155: Fix création robuste + UI d'édition groupe (nom, prompt, membres, IA/Humain)
// V107.11: Chat intégré inline dans chaque groupe

import React, { useState, useEffect, useRef, memo, useCallback } from 'react';
import { Users, Plus, X, Search, Check, Bot, UserCircle, Trash2, ChevronDown, ChevronUp, Copy, MessageSquare, Send, RefreshCw, Edit2, Save, UserPlus } from 'lucide-react';
import { renderTextWithLinks } from '../chat/ChatBubbles';

// === AI / Human Toggle Switch ===
const AiHumanSwitch = memo(({ isAi, onToggle, size = 'normal' }) => {
  const h = size === 'small' ? 28 : 36;
  const w = size === 'small' ? 64 : 80;
  const dot = size === 'small' ? 20 : 28;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <span style={{ fontSize: size === 'small' ? '11px' : '12px', color: !isAi ? '#D91CD2' : 'rgba(255,255,255,0.35)', fontWeight: !isAi ? '700' : '500', transition: 'all 0.2s' }}>
        <UserCircle size={size === 'small' ? 12 : 14} style={{ marginRight: '3px', verticalAlign: 'middle' }} /> Humain
      </span>
      <button onClick={onToggle} style={{
        width: `${w}px`, height: `${h}px`, borderRadius: `${h}px`,
        background: isAi ? 'linear-gradient(135deg, #D91CD2, #8b5cf6)' : 'rgba(255,255,255,0.12)',
        border: 'none', cursor: 'pointer', position: 'relative',
        transition: 'all 0.3s ease', boxShadow: isAi ? '0 0 12px rgba(217,28,210,0.3)' : 'none',
      }}>
        <div style={{
          width: `${dot}px`, height: `${dot}px`, borderRadius: '50%', background: '#fff',
          position: 'absolute', top: '50%', transform: 'translateY(-50%)',
          left: isAi ? `${w - dot - 4}px` : '4px', transition: 'left 0.3s ease',
          boxShadow: '0 2px 4px rgba(0,0,0,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          {isAi ? <Bot size={size === 'small' ? 10 : 14} color="#D91CD2" /> : <UserCircle size={size === 'small' ? 10 : 14} color="#666" />}
        </div>
      </button>
      <span style={{ fontSize: size === 'small' ? '11px' : '12px', color: isAi ? '#D91CD2' : 'rgba(255,255,255,0.35)', fontWeight: isAi ? '700' : '500', transition: 'all 0.2s' }}>
        <Bot size={size === 'small' ? 12 : 14} style={{ marginRight: '3px', verticalAlign: 'middle' }} /> IA
      </span>
    </div>
  );
});
AiHumanSwitch.displayName = 'AiHumanSwitch';

// === Member Selector ===
const MemberSelector = memo(({ contacts = [], selectedIds, onToggleMember }) => {
  const [search, setSearch] = useState('');
  const filtered = contacts.filter(c => {
    const q = search.toLowerCase();
    return (c.name || '').toLowerCase().includes(q) || (c.email || '').toLowerCase().includes(q) || (c.whatsapp || '').toLowerCase().includes(q);
  });

  return (
    <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '12px', overflow: 'hidden' }}>
      <div style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.04)', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <Search size={14} color="rgba(255,255,255,0.3)" />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Rechercher un membre..."
          style={{ flex: 1, background: 'none', border: 'none', color: '#fff', fontSize: '12px', outline: 'none' }} />
        {selectedIds.size > 0 && (
          <span style={{ padding: '2px 8px', borderRadius: '10px', background: 'rgba(217,28,210,0.15)', color: '#D91CD2', fontSize: '10px', fontWeight: '700' }}>
            {selectedIds.size}
          </span>
        )}
      </div>
      <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
        {filtered.length === 0 ? (
          <p style={{ padding: '16px', textAlign: 'center', color: 'rgba(255,255,255,0.25)', fontSize: '12px', margin: 0 }}>Aucun contact trouvé</p>
        ) : filtered.map(contact => {
          const cid = contact.id || contact.email || contact.whatsapp;
          const isSelected = selectedIds.has(cid);
          return (
            <button key={cid} onClick={() => onToggleMember(cid)} style={{
              width: '100%', padding: '10px 12px', display: 'flex', alignItems: 'center', gap: '10px',
              background: isSelected ? 'rgba(217,28,210,0.06)' : 'transparent',
              border: 'none', borderBottom: '1px solid rgba(255,255,255,0.03)', cursor: 'pointer', textAlign: 'left', transition: 'background 0.15s',
            }}>
              <div style={{
                width: '32px', height: '32px', borderRadius: '50%',
                background: isSelected ? 'linear-gradient(135deg, #D91CD2, #8b5cf6)' : 'rgba(255,255,255,0.08)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#fff', fontSize: '12px', fontWeight: '700',
                border: isSelected ? '2px solid #D91CD2' : '2px solid transparent', transition: 'all 0.2s',
              }}>
                {isSelected ? <Check size={14} /> : (contact.name || '?')[0].toUpperCase()}
              </div>
              <div style={{ flex: 1 }}>
                <p style={{ color: '#fff', fontSize: '12px', fontWeight: '600', margin: 0 }}>{contact.name || 'Sans nom'}</p>
                <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: '10px', margin: '2px 0 0' }}>{contact.email || contact.whatsapp || ''}</p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
});
MemberSelector.displayName = 'MemberSelector';

// === V107.11: Group Chat Panel — interface chat inline pour les groupes ===
const GroupChatPanel = memo(({ group, API, coachEmail, onClose }) => {
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef(null);
  const sessionId = group.session_id || `grp_${group.id.slice(0, 8)}`;

  const loadMessages = useCallback(async () => {
    if (!API) return;
    setLoading(true);
    try {
      const res = await fetch(`${API}/chat/sessions/${sessionId}/messages`, {
        headers: { 'X-User-Email': coachEmail || '' }
      });
      if (res.ok) {
        const data = await res.json();
        setMessages(data || []);
      }
    } catch (e) { console.error('[V107.11] Erreur chargement messages groupe:', e); }
    setLoading(false);
  }, [API, sessionId, coachEmail]);

  useEffect(() => { loadMessages(); }, [loadMessages]);
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  // Polling toutes les 10s
  useEffect(() => {
    const interval = setInterval(loadMessages, 10000);
    return () => clearInterval(interval);
  }, [loadMessages]);

  const handleSend = async () => {
    const msg = newMessage.trim();
    if (!msg || !API || sending) return;
    setSending(true);
    try {
      const res = await fetch(`${API}/chat/coach-response`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-Email': coachEmail || '' },
        body: JSON.stringify({ session_id: sessionId, message: msg, coach_name: 'Coach' }),
      });
      if (res.ok) {
        setNewMessage('');
        await loadMessages();
      }
    } catch (e) { console.error('[V107.11] Erreur envoi message groupe:', e); }
    setSending(false);
  };

  return (
    <div style={{
      background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(217,28,210,0.2)',
      borderRadius: '12px', overflow: 'hidden', marginTop: '8px',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 14px', borderBottom: '1px solid rgba(255,255,255,0.06)',
        background: 'linear-gradient(135deg, rgba(217,28,210,0.08), rgba(139,92,246,0.04))',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Users size={14} color="#D91CD2" />
          <span style={{ color: '#fff', fontSize: '12px', fontWeight: '700' }}>{group.name}</span>
          <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '10px' }}>
            {messages.length} msg
          </span>
        </div>
        <div style={{ display: 'flex', gap: '4px' }}>
          <button onClick={loadMessages} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.3)', cursor: 'pointer', padding: '2px' }}>
            <RefreshCw size={12} />
          </button>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.3)', cursor: 'pointer', padding: '2px' }}>
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div style={{ maxHeight: '300px', overflowY: 'auto', padding: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {loading && messages.length === 0 ? (
          <p style={{ color: 'rgba(255,255,255,0.2)', fontSize: '11px', textAlign: 'center', margin: '20px 0' }}>Chargement...</p>
        ) : messages.length === 0 ? (
          <p style={{ color: 'rgba(255,255,255,0.15)', fontSize: '11px', textAlign: 'center', margin: '20px 0' }}>
            Aucun message. Envoyez le premier message au groupe !
          </p>
        ) : messages.map((msg, idx) => {
          const isCoach = msg.sender_type === 'coach' || msg.role === 'coach';
          const isAI = msg.sender_type === 'assistant' || msg.role === 'assistant';
          const isSystem = msg.sender_type === 'system';

          if (isSystem) {
            return (
              <div key={msg.id || idx} style={{ textAlign: 'center' }}>
                <span style={{ fontSize: '10px', color: 'rgba(255,255,255,0.25)', padding: '2px 10px', borderRadius: '10px', background: 'rgba(139,92,246,0.06)' }}>
                  {msg.content || msg.text || ''}
                </span>
              </div>
            );
          }

          return (
            <div key={msg.id || idx} style={{ display: 'flex', justifyContent: isCoach || isAI ? 'flex-end' : 'flex-start' }}>
              <div style={{
                maxWidth: '80%', padding: '8px 12px', borderRadius: isCoach || isAI ? '12px 4px 12px 12px' : '4px 12px 12px 12px',
                background: isCoach ? '#D91CD2' : isAI ? 'rgba(139,92,246,0.3)' : 'rgba(255,255,255,0.06)',
              }}>
                <p style={{ fontSize: '9px', fontWeight: '600', opacity: 0.5, color: '#fff', margin: '0 0 3px' }}>
                  {isCoach ? 'Vous' : isAI ? 'IA' : (msg.sender_name || 'Membre')}
                </p>
                <p style={{ fontSize: '12px', color: '#fff', margin: 0, lineHeight: '1.4', wordBreak: 'break-word' }}>
                  {renderTextWithLinks(msg.content || msg.text || msg.message || '')}
                </p>
                <p style={{ fontSize: '9px', color: 'rgba(255,255,255,0.3)', margin: '4px 0 0', textAlign: 'right' }}>
                  {(() => {
                    const d = msg.timestamp || msg.createdAt || msg.created_at;
                    if (!d) return '';
                    try { return new Date(d).toLocaleString('fr-CH', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }); } catch { return ''; }
                  })()}
                </p>
              </div>
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div style={{
        display: 'flex', gap: '8px', alignItems: 'center',
        padding: '10px 12px', borderTop: '1px solid rgba(255,255,255,0.06)',
      }}>
        <input
          value={newMessage}
          onChange={e => setNewMessage(e.target.value)}
          onKeyPress={e => e.key === 'Enter' && handleSend()}
          placeholder="Message au groupe..."
          style={{
            flex: 1, padding: '8px 0', background: 'transparent', border: 'none',
            color: '#fff', fontSize: '12px', outline: 'none',
          }}
        />
        <button
          onClick={handleSend}
          disabled={!newMessage.trim() || sending}
          style={{
            background: 'none', border: 'none', cursor: newMessage.trim() && !sending ? 'pointer' : 'not-allowed',
            color: newMessage.trim() && !sending ? '#D91CD2' : 'rgba(255,255,255,0.15)',
            padding: '4px', transition: 'color 0.2s',
          }}
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
});
GroupChatPanel.displayName = 'GroupChatPanel';

// === Group Card — V155: ajout bouton Modifier ===
const GroupCard = memo(({ group, onSelect, onDelete, onCopyLink, onOpenChat, onEdit, isActive, copiedId }) => {
  const memberCount = (group.member_ids || []).length;
  // v108: Afficher les noms des membres résolus depuis members_info
  const membersInfo = group.members_info || [];
  const memberNames = membersInfo.map(m => m.name || m.email || 'Inconnu').filter(Boolean);
  const membersSummary = memberNames.length > 0
    ? memberNames.slice(0, 3).join(', ') + (memberNames.length > 3 ? ` +${memberNames.length - 3}` : '')
    : '';
  const origin = typeof window !== 'undefined' ? window.location.origin : '';
  const groupLink = group.link_token ? `${origin}/?group=${group.link_token}` : '';

  return (
    <div onClick={() => onSelect(group)} style={{
      width: '100%', padding: '12px', borderRadius: '12px',
      background: isActive ? 'rgba(217,28,210,0.08)' : '#1A1A1A',
      border: isActive ? '1px solid rgba(217,28,210,0.3)' : '1px solid rgba(255,255,255,0.06)',
      cursor: 'pointer', textAlign: 'left', display: 'flex', alignItems: 'center', gap: '12px', transition: 'all 0.2s',
    }}>
      <div style={{
        width: '40px', height: '40px', borderRadius: '12px',
        background: 'linear-gradient(135deg, rgba(217,28,210,0.15), rgba(139,92,246,0.1))',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>
        <Users size={18} color="#D91CD2" />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ color: '#fff', fontSize: '13px', fontWeight: '600', margin: 0 }}>{group.name || 'Groupe sans nom'}</p>
        <p style={{ color: 'rgba(255,255,255,0.35)', fontSize: '10px', margin: '2px 0 0' }}>
          {memberCount} membre{memberCount > 1 ? 's' : ''} {group.is_ai_active ? '🤖 IA' : '👤 Humain'}
        </p>
        {membersSummary && (
          <p style={{ color: 'rgba(255,255,255,0.25)', fontSize: '9px', margin: '2px 0 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {membersSummary}
          </p>
        )}
        {group.system_prompt && (
          <p style={{ color: 'rgba(139,92,246,0.5)', fontSize: '9px', margin: '2px 0 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            <MessageSquare size={8} style={{ verticalAlign: 'middle', marginRight: '3px' }} />
            {group.system_prompt.slice(0, 50)}{group.system_prompt.length > 50 ? '...' : ''}
          </p>
        )}
      </div>
      <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
        {/* V155: Bouton Modifier */}
        <button onClick={e => { e.stopPropagation(); onEdit(group); }}
          title="Modifier le groupe"
          style={{
            background: 'none', border: 'none', padding: '4px', borderRadius: '6px',
            color: 'rgba(255,255,255,0.3)', cursor: 'pointer', transition: 'all 0.2s',
          }}>
          <Edit2 size={14} />
        </button>
        {/* V107.11: Bouton Chat */}
        <button onClick={e => { e.stopPropagation(); onOpenChat(group); }}
          title="Ouvrir le chat du groupe"
          style={{
            background: isActive ? 'rgba(217,28,210,0.2)' : 'none', border: 'none', padding: '4px', borderRadius: '6px',
            color: isActive ? '#D91CD2' : 'rgba(255,255,255,0.3)', cursor: 'pointer', transition: 'all 0.2s',
          }}>
          <MessageSquare size={14} />
        </button>
        {groupLink && (
          <button onClick={e => { e.stopPropagation(); onCopyLink(group.id, groupLink); }}
            title="Copier le lien du groupe"
            style={{ background: 'none', border: 'none', padding: '4px', color: copiedId === group.id ? '#22c55e' : 'rgba(255,255,255,0.3)', cursor: 'pointer' }}>
            {copiedId === group.id ? <Check size={14} /> : <Copy size={14} />}
          </button>
        )}
        <button onClick={e => { e.stopPropagation(); onDelete(group.id); }}
          style={{ background: 'none', border: 'none', color: 'rgba(239,68,68,0.4)', cursor: 'pointer', padding: '4px' }}>
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
});
GroupCard.displayName = 'GroupCard';

// === V155: Group Form — réutilisé pour Création ET Édition ===
const GroupForm = memo(({
  mode = 'create', // 'create' | 'edit'
  initialName = '', initialPrompt = '', initialMembers = new Set(), initialIsAi = true,
  contacts = [], API, coachEmail,
  onSubmit, onCancel,
}) => {
  const [groupName, setGroupName] = useState(initialName);
  const [systemPrompt, setSystemPrompt] = useState(initialPrompt);
  const [selectedMembers, setSelectedMembers] = useState(initialMembers);
  const [isAiActive, setIsAiActive] = useState(initialIsAi);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [generatingPrompt, setGeneratingPrompt] = useState(false);

  const toggleMember = useCallback((memberId) => {
    setSelectedMembers(prev => { const next = new Set(prev); if (next.has(memberId)) next.delete(memberId); else next.add(memberId); return next; });
  }, []);

  const handleGeneratePrompt = async () => {
    if (!groupName.trim() || !API) return;
    setGeneratingPrompt(true);
    try {
      const res = await fetch(`${API}/ai/enhance-text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-Email': coachEmail || '' },
        body: JSON.stringify({
          text: `Génère un prompt système expert pour un assistant IA dans un groupe appelé "${groupName.trim()}". Le prompt doit définir la personnalité, le ton et l'expertise de l'IA. Style Afroboost : motivant, chaleureux, professionnel. Maximum 3 phrases.`,
          style: 'expert'
        }),
      });
      if (res.ok) {
        const data = await res.json();
        const enhanced = data.enhanced_text || data.enhanced || data.text || data.result || '';
        if (enhanced) setSystemPrompt(enhanced);
      }
    } catch (e) { console.error('[V155] Erreur génération prompt:', e); }
    setGeneratingPrompt(false);
  };

  const handleSubmit = async () => {
    if (!groupName.trim() || !API) return;
    setLoading(true);
    setError('');
    try {
      const result = await onSubmit({
        name: groupName.trim(),
        members: Array.from(selectedMembers),
        system_prompt: systemPrompt.trim(),
        is_ai_active: isAiActive,
      });
      if (result?.error) {
        setError(result.error);
      }
    } catch (e) {
      console.error(`[V155] Erreur ${mode} groupe:`, e);
      setError(`Erreur: ${e.message || 'Veuillez réessayer'}`);
    }
    setLoading(false);
  };

  const isEdit = mode === 'edit';

  return (
    <div style={{
      background: isEdit ? 'rgba(139,92,246,0.04)' : 'rgba(217,28,210,0.04)',
      border: `1px solid ${isEdit ? 'rgba(139,92,246,0.2)' : 'rgba(217,28,210,0.15)'}`,
      borderRadius: '12px', padding: '14px', display: 'flex', flexDirection: 'column', gap: '12px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ color: isEdit ? '#8b5cf6' : '#D91CD2', fontSize: '12px', fontWeight: '700', display: 'flex', alignItems: 'center', gap: '6px' }}>
          {isEdit ? <><Edit2 size={12} /> Modifier le groupe</> : 'Nouveau groupe'}
        </span>
        <button onClick={onCancel} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.3)', cursor: 'pointer', padding: '2px' }}>
          <X size={14} />
        </button>
      </div>

      {/* Error message */}
      {error && (
        <div style={{
          padding: '8px 12px', borderRadius: '8px', background: 'rgba(239,68,68,0.1)',
          border: '1px solid rgba(239,68,68,0.2)', color: '#ef4444', fontSize: '11px',
        }}>
          {error}
        </div>
      )}

      {/* Nom */}
      <div>
        <label style={{ display: 'block', color: 'rgba(255,255,255,0.5)', fontSize: '10px', fontWeight: 600, marginBottom: '4px' }}>NOM DU GROUPE</label>
        <input value={groupName} onChange={e => setGroupName(e.target.value)} placeholder="Ex: Marathon, Diete, VIP..."
          style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', color: '#fff', fontSize: '13px', outline: 'none', boxSizing: 'border-box' }}
          onFocus={e => e.target.style.borderColor = 'rgba(217,28,210,0.3)'}
          onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.08)'} />
      </div>

      {/* Prompt Systeme IA */}
      <div>
        <label style={{ display: 'block', color: 'rgba(255,255,255,0.5)', fontSize: '10px', fontWeight: 600, marginBottom: '4px' }}>
          PROMPT SYSTEME IA (personnalite de l'IA pour ce groupe)
        </label>
        <textarea value={systemPrompt} onChange={e => setSystemPrompt(e.target.value)}
          placeholder="Ex: Tu es un coach sportif expert en marathon. Reponds avec motivation et donne des plans d'entrainement personnalises..."
          rows={3}
          style={{
            width: '100%', padding: '10px 12px', borderRadius: '8px', background: 'rgba(139,92,246,0.04)',
            border: '1px solid rgba(139,92,246,0.15)', color: '#fff', fontSize: '12px', outline: 'none',
            boxSizing: 'border-box', resize: 'vertical', fontFamily: 'inherit',
          }}
          onFocus={e => e.target.style.borderColor = 'rgba(139,92,246,0.4)'}
          onBlur={e => e.target.style.borderColor = 'rgba(139,92,246,0.15)'} />
        {/* Bouton Générer Prompt Maître */}
        <button onClick={handleGeneratePrompt} disabled={!groupName.trim() || generatingPrompt}
          style={{
            marginTop: '8px', padding: '10px 20px', borderRadius: '24px',
            background: groupName.trim() && !generatingPrompt
              ? 'linear-gradient(135deg, #D91CD2, #8b5cf6)'
              : 'rgba(255,255,255,0.06)',
            border: groupName.trim() && !generatingPrompt
              ? '1px solid rgba(217,28,210,0.6)'
              : '1px solid rgba(255,255,255,0.1)',
            color: groupName.trim() && !generatingPrompt ? '#fff' : 'rgba(255,255,255,0.25)',
            fontSize: '12px', fontWeight: '700', letterSpacing: '0.3px',
            cursor: groupName.trim() && !generatingPrompt ? 'pointer' : 'not-allowed',
            display: 'flex', alignItems: 'center', gap: '8px',
            transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
            width: 'fit-content',
            boxShadow: groupName.trim() && !generatingPrompt
              ? '0 0 20px rgba(217, 28, 210, 0.4), 0 0 40px rgba(217, 28, 210, 0.15), inset 0 1px 0 rgba(255,255,255,0.15)'
              : 'none',
            textShadow: groupName.trim() && !generatingPrompt ? '0 0 8px rgba(255,255,255,0.5)' : 'none',
          }}
          onMouseEnter={e => { if (groupName.trim() && !generatingPrompt) { e.currentTarget.style.boxShadow = '0 0 30px rgba(217, 28, 210, 0.6), 0 0 60px rgba(217, 28, 210, 0.25), inset 0 1px 0 rgba(255,255,255,0.2)'; e.currentTarget.style.transform = 'translateY(-1px)'; }}}
          onMouseLeave={e => { if (groupName.trim() && !generatingPrompt) { e.currentTarget.style.boxShadow = '0 0 20px rgba(217, 28, 210, 0.4), 0 0 40px rgba(217, 28, 210, 0.15), inset 0 1px 0 rgba(255,255,255,0.15)'; e.currentTarget.style.transform = 'translateY(0)'; }}}
        >
          {generatingPrompt ? '⏳ Génération en cours...' : '✨ Générer Prompt Maître'}
        </button>
      </div>

      {/* Switch IA / Humain */}
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <AiHumanSwitch isAi={isAiActive} onToggle={() => setIsAiActive(!isAiActive)} size="small" />
      </div>

      {/* Selecteur de membres */}
      <div>
        <label style={{ display: 'block', color: 'rgba(255,255,255,0.5)', fontSize: '10px', fontWeight: 600, marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
          {isEdit && <UserPlus size={10} />}
          MEMBRES ({selectedMembers.size} selectionne{selectedMembers.size > 1 ? 's' : ''})
        </label>
        <MemberSelector contacts={contacts} selectedIds={selectedMembers} onToggleMember={toggleMember} />
      </div>

      {/* Bouton submit */}
      <button onClick={handleSubmit} disabled={!groupName.trim() || loading} style={{
        padding: '10px', borderRadius: '10px',
        background: groupName.trim() && !loading
          ? (isEdit ? 'linear-gradient(135deg, #8b5cf6, #D91CD2)' : 'linear-gradient(135deg, #D91CD2, #9333ea)')
          : 'rgba(255,255,255,0.06)',
        border: 'none', color: '#fff', fontSize: '12px', fontWeight: '700',
        cursor: groupName.trim() && !loading ? 'pointer' : 'not-allowed', opacity: groupName.trim() && !loading ? 1 : 0.4,
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
      }}>
        {loading
          ? (isEdit ? 'Sauvegarde...' : 'Creation...')
          : isEdit
            ? <><Save size={14} /> Sauvegarder les modifications</>
            : <><Plus size={14} /> Creer le groupe</>
        }
      </button>
    </div>
  );
});
GroupForm.displayName = 'GroupForm';

// === Main GroupChatModule (V155: CRUD complet + Edition) ===
const GroupChatModule = memo(({ contacts = [], API, coachEmail }) => {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingGroup, setEditingGroup] = useState(null); // V155: groupe en cours d'édition
  const [expanded, setExpanded] = useState(true);
  const [activeGroupId, setActiveGroupId] = useState(null);
  const [chatGroupId, setChatGroupId] = useState(null);
  const [copiedId, setCopiedId] = useState(null);

  // Charger les groupes au mount
  useEffect(() => {
    if (!API) return;
    const fetchGroups = async () => {
      try {
        const res = await fetch(`${API}/chat/groups`, { headers: { 'X-User-Email': coachEmail || '' } });
        if (res.ok) setGroups(await res.json());
      } catch (e) { console.error('[V101] Erreur fetch groupes:', e); }
    };
    fetchGroups();
  }, [API, coachEmail]);

  // V155: Création de groupe — avec feedback erreur
  const handleCreate = async (formData) => {
    if (!API) return { error: 'API non disponible' };
    try {
      const res = await fetch(`${API}/chat/groups`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-Email': coachEmail || '' },
        body: JSON.stringify({ name: formData.name, members: formData.members, system_prompt: formData.system_prompt, is_ai_active: formData.is_ai_active }),
      });
      if (res.ok) {
        const newGroup = await res.json();
        setGroups(prev => [newGroup, ...prev]);
        setShowCreateForm(false);
        return {};
      } else {
        const errData = await res.json().catch(() => ({}));
        const errMsg = errData.detail || `Erreur ${res.status}`;
        console.error('[V155] Erreur création groupe:', errMsg);
        return { error: errMsg };
      }
    } catch (e) {
      console.error('[V155] Erreur réseau création groupe:', e);
      return { error: `Erreur réseau: ${e.message}` };
    }
  };

  // V155: Mise à jour de groupe
  const handleUpdate = async (formData) => {
    if (!API || !editingGroup) return { error: 'API non disponible' };
    try {
      const res = await fetch(`${API}/chat/groups/${editingGroup.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-User-Email': coachEmail || '' },
        body: JSON.stringify({
          name: formData.name,
          member_ids: formData.members,
          system_prompt: formData.system_prompt,
          is_ai_active: formData.is_ai_active,
        }),
      });
      if (res.ok) {
        const updated = await res.json();
        setGroups(prev => prev.map(g => g.id === editingGroup.id ? { ...g, ...updated } : g));
        setEditingGroup(null);
        return {};
      } else {
        const errData = await res.json().catch(() => ({}));
        const errMsg = errData.detail || `Erreur ${res.status}`;
        console.error('[V155] Erreur mise à jour groupe:', errMsg);
        return { error: errMsg };
      }
    } catch (e) {
      console.error('[V155] Erreur réseau mise à jour groupe:', e);
      return { error: `Erreur réseau: ${e.message}` };
    }
  };

  const handleDelete = async (groupId) => {
    if (!API) return;
    if (!window.confirm('Supprimer ce groupe ?')) return;
    try {
      await fetch(`${API}/chat/groups/${groupId}`, { method: 'DELETE', headers: { 'X-User-Email': coachEmail || '' } });
      setGroups(prev => prev.filter(g => g.id !== groupId));
      if (editingGroup?.id === groupId) setEditingGroup(null);
      if (chatGroupId === groupId) setChatGroupId(null);
    } catch (e) { console.error('[V155] Erreur suppression groupe:', e); }
  };

  // V155: Ouvrir l'édition d'un groupe
  const handleStartEdit = useCallback((group) => {
    setEditingGroup(group);
    setShowCreateForm(false); // Fermer le formulaire de création si ouvert
    setChatGroupId(null); // Fermer le chat si ouvert
  }, []);

  const handleCopyLink = (groupId, link) => {
    navigator.clipboard.writeText(link).catch(() => {});
    setCopiedId(groupId);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div style={{ background: '#1A1A1A', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '16px', overflow: 'hidden' }}>
      {/* Header */}
      <button onClick={() => setExpanded(!expanded)} style={{
        width: '100%', padding: '14px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: 'none', border: 'none', cursor: 'pointer',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ width: '28px', height: '28px', borderRadius: '8px', background: 'linear-gradient(135deg, #D91CD2, #9333ea)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Users size={14} color="#fff" />
          </div>
          <span style={{ color: '#fff', fontSize: '14px', fontWeight: '700' }}>Groupes de Chat ({groups.length})</span>
        </div>
        {expanded ? <ChevronUp size={16} color="rgba(255,255,255,0.3)" /> : <ChevronDown size={16} color="rgba(255,255,255,0.3)" />}
      </button>

      {expanded && (
        <div style={{ padding: '0 16px 16px' }}>
          {/* Liste des groupes */}
          {groups.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '12px' }}>
              {groups.map(g => (
                <React.Fragment key={g.id}>
                  <GroupCard group={g} isActive={g.id === chatGroupId}
                    onSelect={(grp) => { setChatGroupId(prev => prev === grp.id ? null : grp.id); setActiveGroupId(grp.id); }}
                    onOpenChat={(grp) => setChatGroupId(prev => prev === grp.id ? null : grp.id)}
                    onEdit={handleStartEdit}
                    onDelete={handleDelete}
                    onCopyLink={handleCopyLink} copiedId={copiedId} />

                  {/* V155: Edit form inline sous le groupe sélectionné */}
                  {editingGroup?.id === g.id && (
                    <GroupForm
                      mode="edit"
                      initialName={g.name || ''}
                      initialPrompt={g.system_prompt || ''}
                      initialMembers={new Set(g.member_ids || [])}
                      initialIsAi={g.is_ai_active !== false}
                      contacts={contacts}
                      API={API}
                      coachEmail={coachEmail}
                      onSubmit={handleUpdate}
                      onCancel={() => setEditingGroup(null)}
                    />
                  )}

                  {/* V107.11: Chat panel inline sous le groupe actif */}
                  {chatGroupId === g.id && !editingGroup && (
                    <GroupChatPanel
                      group={g}
                      API={API}
                      coachEmail={coachEmail}
                      onClose={() => setChatGroupId(null)}
                    />
                  )}
                </React.Fragment>
              ))}
            </div>
          )}

          {groups.length === 0 && !showCreateForm && (
            <p style={{ color: 'rgba(255,255,255,0.2)', fontSize: '12px', textAlign: 'center', margin: '0 0 12px' }}>
              Aucun groupe. Creez-en un pour regrouper vos abonnes.
            </p>
          )}

          {/* Bouton ou formulaire de creation */}
          {!showCreateForm && !editingGroup ? (
            <button onClick={() => setShowCreateForm(true)} style={{
              width: '100%', padding: '10px', borderRadius: '10px',
              background: 'rgba(217,28,210,0.08)', border: '1px dashed rgba(217,28,210,0.25)',
              color: '#D91CD2', fontSize: '12px', fontWeight: '600',
              cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px', transition: 'all 0.2s',
            }}
              onMouseEnter={e => e.currentTarget.style.background = 'rgba(217,28,210,0.15)'}
              onMouseLeave={e => e.currentTarget.style.background = 'rgba(217,28,210,0.08)'}
            >
              <Plus size={14} /> Creer un groupe
            </button>
          ) : showCreateForm && (
            <GroupForm
              mode="create"
              contacts={contacts}
              API={API}
              coachEmail={coachEmail}
              onSubmit={handleCreate}
              onCancel={() => setShowCreateForm(false)}
            />
          )}
        </div>
      )}
    </div>
  );
});

GroupChatModule.displayName = 'GroupChatModule';
export { AiHumanSwitch, MemberSelector, GroupCard, GroupChatPanel, GroupForm };
export default GroupChatModule;

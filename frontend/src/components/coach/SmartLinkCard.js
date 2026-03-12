// SmartLinkCard.js — v98.2: Carte premium Liens Intelligents
// Design: fond anthracite #1A1A1A, glow violet, gradient overlay, checkbox sélection
import React, { memo, useState } from 'react';
import { Copy, Check, ExternalLink, Trash2, Edit2, Eye, MessageCircle, Zap } from 'lucide-react';

const LEAD_TYPES = [
  { value: 'participant', label: 'Participant', color: '#22c55e', icon: '\u{1F3C3}', gradient: 'linear-gradient(135deg, #22c55e, #16a34a)' },
  { value: 'partner', label: 'Partenaire', color: '#f59e0b', icon: '\u{1F91D}', gradient: 'linear-gradient(135deg, #f59e0b, #d97706)' },
  { value: 'collaboration', label: 'Collaboration', color: '#3b82f6', icon: '\u{1F3AF}', gradient: 'linear-gradient(135deg, #3b82f6, #2563eb)' },
  { value: 'question', label: 'Question', color: '#a78bfa', icon: '\u{2753}', gradient: 'linear-gradient(135deg, #a78bfa, #8b5cf6)' },
];

const SmartLinkCard = memo(({ link, copiedLinkId, onCopy, onDelete, onEdit, onPreview, selected, onToggleSelect }) => {
  const [hovered, setHovered] = useState(false);

  // Robust ID: fallback chain
  const linkId = link.id || link._id || link.link_token || '';
  const linkToken = link.link_token || link.token || '';
  const fullUrl = `${window.location.origin}/?link=${linkToken}`;
  const usageCount = link.participant_count || 0;
  const createdAt = link.created_at || link.createdAt || '';
  const leadType = LEAD_TYPES.find(l => l.value === (link.lead_type || 'participant')) || LEAD_TYPES[0];
  const questionsCount = (link.tunnel_questions || []).length;
  const actionsCount = (link.end_actions || []).length;
  const isCopied = copiedLinkId === linkId;
  const hasPrompt = !!(link.custom_prompt || link.customPrompt);
  const hasTunnel = questionsCount > 0;

  const formatDate = (d) => {
    try {
      const date = new Date(d);
      return isNaN(date.getTime()) ? '\u2014' : new Intl.DateTimeFormat('fr-CH', { day: '2-digit', month: 'short', year: '2-digit' }).format(date);
    } catch { return '\u2014'; }
  };

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: 'relative',
        background: selected
          ? 'linear-gradient(135deg, #1A1A1A 0%, #261030 100%)'
          : hovered
            ? 'linear-gradient(135deg, #1A1A1A 0%, #1f1028 100%)'
            : '#1A1A1A',
        border: selected
          ? '1.5px solid rgba(217,28,210,0.6)'
          : hovered
            ? '1px solid rgba(217,28,210,0.35)'
            : '1px solid rgba(255,255,255,0.08)',
        borderRadius: '16px',
        overflow: 'hidden',
        transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        boxShadow: selected
          ? '0 0 24px rgba(217,28,210,0.2), 0 8px 32px rgba(0,0,0,0.4)'
          : hovered
            ? '0 0 16px rgba(217,28,210,0.12), 0 8px 24px rgba(0,0,0,0.3)'
            : '0 2px 8px rgba(0,0,0,0.3)',
      }}
    >
      {/* Top glow gradient bar */}
      <div style={{
        height: hovered || selected ? '4px' : '3px',
        background: `linear-gradient(90deg, ${leadType.color}, #D91CD2, ${leadType.color})`,
        opacity: hovered || selected ? 1 : 0.4,
        transition: 'all 0.3s',
      }} />

      {/* Subtle violet glow overlay at top */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, height: '60px',
        background: 'linear-gradient(180deg, rgba(217,28,210,0.06) 0%, transparent 100%)',
        pointerEvents: 'none',
        opacity: hovered || selected ? 1 : 0,
        transition: 'opacity 0.3s',
      }} />

      <div style={{ padding: '16px 18px 14px', position: 'relative' }}>
        {/* Row 1: Checkbox + Title + Badge */}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', marginBottom: '12px' }}>
          {/* Checkbox */}
          {onToggleSelect && (
            <button
              onClick={(e) => { e.stopPropagation(); onToggleSelect(linkId); }}
              style={{
                width: '22px', height: '22px', borderRadius: '6px', flexShrink: 0,
                marginTop: '2px',
                background: selected ? 'linear-gradient(135deg, #D91CD2, #9333ea)' : 'rgba(255,255,255,0.06)',
                border: selected ? 'none' : '1.5px solid rgba(255,255,255,0.15)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer', transition: 'all 0.2s',
                boxShadow: selected ? '0 0 8px rgba(217,28,210,0.4)' : 'none',
              }}
            >
              {selected && <Check size={13} color="#fff" strokeWidth={3} />}
            </button>
          )}

          {/* Icon + Title */}
          <div style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: '40px', height: '40px', borderRadius: '12px',
              background: `${leadType.color}12`,
              border: `1px solid ${leadType.color}28`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '18px', flexShrink: 0,
              boxShadow: hovered ? `0 0 14px ${leadType.color}20` : 'none',
              transition: 'all 0.3s',
            }}>
              {leadType.icon}
            </div>
            <div style={{ minWidth: 0 }}>
              <p style={{
                color: '#FFFFFF', fontSize: '15px', fontWeight: '700', margin: 0,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                lineHeight: '1.3',
              }}>
                {link.title || 'Lien sans titre'}
              </p>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px', flexWrap: 'wrap' }}>
                <span style={{
                  padding: '2px 10px', borderRadius: '10px',
                  background: `${leadType.color}18`, color: leadType.color,
                  fontSize: '10px', fontWeight: '700', letterSpacing: '0.3px',
                }}>
                  {leadType.label}
                </span>
                <span style={{ color: 'rgba(255,255,255,0.35)', fontSize: '10px' }}>
                  {formatDate(createdAt)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Row 2: Stats — blanc pur & violet néon */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '12px', flexWrap: 'wrap' }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: '5px',
            padding: '5px 12px', borderRadius: '8px',
            background: 'rgba(255,255,255,0.06)',
            border: '1px solid rgba(255,255,255,0.08)',
          }}>
            <Eye size={12} color="#D91CD2" />
            <span style={{ color: '#FFFFFF', fontSize: '13px', fontWeight: '800' }}>{usageCount}</span>
            <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '10px' }}>clic{usageCount !== 1 ? 's' : ''}</span>
          </div>
          {hasTunnel && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: '5px',
              padding: '5px 12px', borderRadius: '8px',
              background: 'rgba(217,28,210,0.08)',
              border: '1px solid rgba(217,28,210,0.18)',
            }}>
              <MessageCircle size={12} color="#D91CD2" />
              <span style={{ color: '#D91CD2', fontSize: '13px', fontWeight: '800' }}>{questionsCount}</span>
              <span style={{ color: 'rgba(217,28,210,0.7)', fontSize: '10px' }}>Q</span>
            </div>
          )}
          {actionsCount > 0 && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: '5px',
              padding: '5px 12px', borderRadius: '8px',
              background: 'rgba(34,197,94,0.08)',
              border: '1px solid rgba(34,197,94,0.18)',
            }}>
              <Zap size={12} color="#22c55e" />
              <span style={{ color: '#22c55e', fontSize: '13px', fontWeight: '800' }}>{actionsCount}</span>
              <span style={{ color: 'rgba(34,197,94,0.7)', fontSize: '10px' }}>A</span>
            </div>
          )}
          {hasPrompt && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: '4px',
              padding: '5px 10px', borderRadius: '8px',
              background: 'rgba(139,92,246,0.08)',
              border: '1px solid rgba(139,92,246,0.18)',
            }}>
              <span style={{ fontSize: '11px' }}>{'\u2728'}</span>
              <span style={{ color: '#a78bfa', fontSize: '10px', fontWeight: '700' }}>IA</span>
            </div>
          )}
        </div>

        {/* Row 3: Prompt preview */}
        {hasPrompt && (
          <div style={{
            padding: '8px 12px', borderRadius: '8px',
            background: 'rgba(139,92,246,0.05)',
            border: '1px solid rgba(139,92,246,0.12)',
            marginBottom: '12px',
          }}>
            <p style={{
              margin: 0, color: 'rgba(167,139,250,0.7)', fontSize: '11px',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {'\u2726'} {link.custom_prompt || link.customPrompt}
            </p>
          </div>
        )}

        {/* Row 4: Actions */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '6px',
          paddingTop: '10px',
          borderTop: '1px solid rgba(255,255,255,0.06)',
        }}>
          <button onClick={() => onEdit(link)}
            style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '5px', padding: '9px 0', borderRadius: '10px', background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.18)', color: '#f59e0b', fontSize: '11px', fontWeight: '600', cursor: 'pointer', transition: 'all 0.2s' }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(245,158,11,0.15)'; e.currentTarget.style.boxShadow = '0 0 10px rgba(245,158,11,0.15)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(245,158,11,0.08)'; e.currentTarget.style.boxShadow = 'none'; }}
          ><Edit2 size={13} /> Modifier</button>

          <button onClick={() => onCopy(linkToken)}
            style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '5px', padding: '9px 0', borderRadius: '10px', background: isCopied ? 'rgba(34,197,94,0.12)' : 'rgba(167,139,250,0.08)', border: isCopied ? '1px solid rgba(34,197,94,0.3)' : '1px solid rgba(167,139,250,0.18)', color: isCopied ? '#22c55e' : '#a78bfa', fontSize: '11px', fontWeight: '600', cursor: 'pointer', transition: 'all 0.2s' }}
            onMouseEnter={e => { if (!isCopied) { e.currentTarget.style.background = 'rgba(167,139,250,0.15)'; e.currentTarget.style.boxShadow = '0 0 10px rgba(167,139,250,0.15)'; } }}
            onMouseLeave={e => { if (!isCopied) { e.currentTarget.style.background = 'rgba(167,139,250,0.08)'; e.currentTarget.style.boxShadow = 'none'; } }}
          >{isCopied ? <><Check size={13} /> OK</> : <><Copy size={13} /> Copier</>}</button>

          <a href={fullUrl} target="_blank" rel="noopener noreferrer"
            style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '5px', padding: '9px 0', borderRadius: '10px', background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.18)', color: '#22c55e', fontSize: '11px', fontWeight: '600', cursor: 'pointer', transition: 'all 0.2s', textDecoration: 'none' }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(34,197,94,0.15)'; e.currentTarget.style.boxShadow = '0 0 10px rgba(34,197,94,0.15)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(34,197,94,0.08)'; e.currentTarget.style.boxShadow = 'none'; }}
          ><ExternalLink size={13} /> Ouvrir</a>

          {onPreview && (
            <button onClick={onPreview}
              style={{ width: '38px', height: '38px', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '10px', flexShrink: 0, background: 'rgba(139,92,246,0.08)', border: '1px solid rgba(139,92,246,0.18)', color: '#8b5cf6', cursor: 'pointer', transition: 'all 0.2s' }}
              onMouseEnter={e => { e.currentTarget.style.background = 'rgba(139,92,246,0.15)'; e.currentTarget.style.boxShadow = '0 0 10px rgba(139,92,246,0.15)'; }}
              onMouseLeave={e => { e.currentTarget.style.background = 'rgba(139,92,246,0.08)'; e.currentTarget.style.boxShadow = 'none'; }}
              title="Aperçu du tunnel"
            ><Eye size={14} /></button>
          )}

          <button onClick={() => onDelete(linkId)}
            style={{ width: '38px', height: '38px', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '10px', flexShrink: 0, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.18)', color: '#ef4444', cursor: 'pointer', transition: 'all 0.2s' }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(239,68,68,0.18)'; e.currentTarget.style.boxShadow = '0 0 10px rgba(239,68,68,0.2)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(239,68,68,0.08)'; e.currentTarget.style.boxShadow = 'none'; }}
            title="Supprimer"
          ><Trash2 size={14} /></button>
        </div>
      </div>
    </div>
  );
});

SmartLinkCard.displayName = 'SmartLinkCard';
export default SmartLinkCard;

// SmartLinkCard.js — v98.1: Carte premium pour liens intelligents
// Design moderne: glow violet, gradient overlay, responsive grid-ready
import React, { memo, useState } from 'react';
import { Copy, Check, ExternalLink, Trash2, Edit2, Link2, Eye, MessageCircle, Zap } from 'lucide-react';

const LEAD_TYPES = [
  { value: 'participant', label: 'Participant', color: '#22c55e', icon: '\u{1F3C3}', gradient: 'linear-gradient(135deg, #22c55e, #16a34a)' },
  { value: 'partner', label: 'Partenaire', color: '#f59e0b', icon: '\u{1F91D}', gradient: 'linear-gradient(135deg, #f59e0b, #d97706)' },
  { value: 'collaboration', label: 'Collaboration', color: '#3b82f6', icon: '\u{1F3AF}', gradient: 'linear-gradient(135deg, #3b82f6, #2563eb)' },
  { value: 'question', label: 'Question', color: '#a78bfa', icon: '\u{2753}', gradient: 'linear-gradient(135deg, #a78bfa, #8b5cf6)' },
];

const SmartLinkCard = memo(({ link, copiedLinkId, onCopy, onDelete, onEdit }) => {
  const [hovered, setHovered] = useState(false);

  const linkToken = link.link_token || link.token || '';
  const fullUrl = `${window.location.origin}/?link=${linkToken}`;
  const usageCount = link.participant_count || 0;
  const createdAt = link.created_at || link.createdAt || '';
  const leadType = LEAD_TYPES.find(l => l.value === (link.lead_type || 'participant')) || LEAD_TYPES[0];
  const questionsCount = (link.tunnel_questions || []).length;
  const actionsCount = (link.end_actions || []).length;
  const isCopied = copiedLinkId === link.id;
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
        background: hovered
          ? 'linear-gradient(135deg, rgba(217,28,210,0.08) 0%, rgba(147,51,234,0.06) 100%)'
          : 'linear-gradient(135deg, rgba(255,255,255,0.025) 0%, rgba(217,28,210,0.015) 100%)',
        border: hovered
          ? '1px solid rgba(217,28,210,0.35)'
          : '1px solid rgba(217,28,210,0.1)',
        borderRadius: '16px',
        padding: '0',
        overflow: 'hidden',
        transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        boxShadow: hovered
          ? '0 0 20px rgba(217,28,210,0.15), 0 8px 32px rgba(0,0,0,0.3)'
          : '0 2px 8px rgba(0,0,0,0.2)',
        cursor: 'default',
      }}
    >
      {/* Top colored accent bar */}
      <div style={{
        height: '3px',
        background: leadType.gradient,
        opacity: hovered ? 1 : 0.5,
        transition: 'opacity 0.3s',
      }} />

      <div style={{ padding: '16px 18px 14px' }}>
        {/* Row 1: Title + Type Badge */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '12px' }}>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: '10px' }}>
            {/* Icon circle */}
            <div style={{
              width: '38px', height: '38px', borderRadius: '12px',
              background: `${leadType.color}15`,
              border: `1px solid ${leadType.color}30`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '18px', flexShrink: 0,
              transition: 'all 0.3s',
              boxShadow: hovered ? `0 0 12px ${leadType.color}25` : 'none',
            }}>
              {leadType.icon}
            </div>
            <div style={{ minWidth: 0 }}>
              <p style={{
                color: '#fff', fontSize: '14px', fontWeight: '700', margin: 0,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                lineHeight: '1.3',
              }}>
                {link.title || 'Lien sans titre'}
              </p>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '3px', flexWrap: 'wrap' }}>
                <span style={{
                  padding: '2px 8px', borderRadius: '10px',
                  background: `${leadType.color}18`, color: leadType.color,
                  fontSize: '10px', fontWeight: '700', letterSpacing: '0.3px',
                }}>
                  {leadType.label}
                </span>
                <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '10px' }}>
                  {formatDate(createdAt)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Row 2: Stats pills */}
        <div style={{
          display: 'flex', gap: '8px', marginBottom: '12px', flexWrap: 'wrap',
        }}>
          {/* Clics */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: '5px',
            padding: '5px 10px', borderRadius: '8px',
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.06)',
          }}>
            <Eye size={12} color="rgba(255,255,255,0.4)" />
            <span style={{ color: '#fff', fontSize: '12px', fontWeight: '700' }}>{usageCount}</span>
            <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '10px' }}>clic{usageCount !== 1 ? 's' : ''}</span>
          </div>

          {/* Tunnel */}
          {hasTunnel && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: '5px',
              padding: '5px 10px', borderRadius: '8px',
              background: 'rgba(217,28,210,0.06)',
              border: '1px solid rgba(217,28,210,0.15)',
            }}>
              <MessageCircle size={12} color="#D91CD2" />
              <span style={{ color: '#D91CD2', fontSize: '12px', fontWeight: '700' }}>{questionsCount}</span>
              <span style={{ color: 'rgba(217,28,210,0.6)', fontSize: '10px' }}>question{questionsCount > 1 ? 's' : ''}</span>
            </div>
          )}

          {/* Actions */}
          {actionsCount > 0 && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: '5px',
              padding: '5px 10px', borderRadius: '8px',
              background: 'rgba(34,197,94,0.06)',
              border: '1px solid rgba(34,197,94,0.15)',
            }}>
              <Zap size={12} color="#22c55e" />
              <span style={{ color: '#22c55e', fontSize: '12px', fontWeight: '700' }}>{actionsCount}</span>
              <span style={{ color: 'rgba(34,197,94,0.6)', fontSize: '10px' }}>action{actionsCount > 1 ? 's' : ''}</span>
            </div>
          )}

          {/* Prompt IA indicator */}
          {hasPrompt && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: '4px',
              padding: '5px 10px', borderRadius: '8px',
              background: 'rgba(139,92,246,0.06)',
              border: '1px solid rgba(139,92,246,0.15)',
            }}>
              <span style={{ fontSize: '10px' }}>{'\u2728'}</span>
              <span style={{ color: 'rgba(167,139,250,0.8)', fontSize: '10px', fontWeight: '600' }}>IA</span>
            </div>
          )}
        </div>

        {/* Row 3: Prompt preview (if exists) */}
        {hasPrompt && (
          <div style={{
            padding: '8px 12px', borderRadius: '8px',
            background: 'rgba(139,92,246,0.04)',
            border: '1px solid rgba(139,92,246,0.1)',
            marginBottom: '12px',
          }}>
            <p style={{
              margin: 0, color: 'rgba(167,139,250,0.6)', fontSize: '11px',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              lineHeight: '1.4',
            }}>
              {'\u2726'} {link.custom_prompt || link.customPrompt}
            </p>
          </div>
        )}

        {/* Row 4: Action buttons */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '6px',
          paddingTop: '10px',
          borderTop: '1px solid rgba(255,255,255,0.04)',
        }}>
          {/* Edit */}
          <button
            onClick={() => onEdit(link)}
            style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
              padding: '8px 0', borderRadius: '10px',
              background: 'rgba(245,158,11,0.06)',
              border: '1px solid rgba(245,158,11,0.15)',
              color: '#f59e0b', fontSize: '11px', fontWeight: '600',
              cursor: 'pointer', transition: 'all 0.2s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(245,158,11,0.12)'; e.currentTarget.style.borderColor = 'rgba(245,158,11,0.3)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(245,158,11,0.06)'; e.currentTarget.style.borderColor = 'rgba(245,158,11,0.15)'; }}
          >
            <Edit2 size={13} /> Modifier
          </button>

          {/* Copy */}
          <button
            onClick={() => onCopy(linkToken)}
            style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
              padding: '8px 0', borderRadius: '10px',
              background: isCopied ? 'rgba(34,197,94,0.12)' : 'rgba(167,139,250,0.06)',
              border: isCopied ? '1px solid rgba(34,197,94,0.3)' : '1px solid rgba(167,139,250,0.15)',
              color: isCopied ? '#22c55e' : '#a78bfa',
              fontSize: '11px', fontWeight: '600',
              cursor: 'pointer', transition: 'all 0.2s',
            }}
            onMouseEnter={e => { if (!isCopied) { e.currentTarget.style.background = 'rgba(167,139,250,0.12)'; e.currentTarget.style.borderColor = 'rgba(167,139,250,0.3)'; }}}
            onMouseLeave={e => { if (!isCopied) { e.currentTarget.style.background = 'rgba(167,139,250,0.06)'; e.currentTarget.style.borderColor = 'rgba(167,139,250,0.15)'; }}}
          >
            {isCopied ? <><Check size={13} /> Copi&eacute;</> : <><Copy size={13} /> Copier</>}
          </button>

          {/* Open */}
          <a
            href={fullUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
              padding: '8px 0', borderRadius: '10px',
              background: 'rgba(34,197,94,0.06)',
              border: '1px solid rgba(34,197,94,0.15)',
              color: '#22c55e', fontSize: '11px', fontWeight: '600',
              cursor: 'pointer', transition: 'all 0.2s',
              textDecoration: 'none',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(34,197,94,0.12)'; e.currentTarget.style.borderColor = 'rgba(34,197,94,0.3)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(34,197,94,0.06)'; e.currentTarget.style.borderColor = 'rgba(34,197,94,0.15)'; }}
          >
            <ExternalLink size={13} /> Ouvrir
          </a>

          {/* Delete */}
          <button
            onClick={() => onDelete(link.id)}
            style={{
              width: '36px', height: '36px', display: 'flex', alignItems: 'center', justifyContent: 'center',
              borderRadius: '10px', flexShrink: 0,
              background: 'rgba(239,68,68,0.06)',
              border: '1px solid rgba(239,68,68,0.15)',
              color: '#ef4444',
              cursor: 'pointer', transition: 'all 0.2s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(239,68,68,0.15)'; e.currentTarget.style.borderColor = 'rgba(239,68,68,0.3)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(239,68,68,0.06)'; e.currentTarget.style.borderColor = 'rgba(239,68,68,0.15)'; }}
            title="Supprimer"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>
    </div>
  );
});

SmartLinkCard.displayName = 'SmartLinkCard';
export default SmartLinkCard;

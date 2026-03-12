// GroupChatModule.js — v99: Module de gestion des groupes de chat
// Créer des groupes, sélectionner des membres, Switch "Réponse IA / Humain"
// Logo Afroboost officiel uniquement

import React, { useState, memo, useCallback } from 'react';
import { Users, Plus, X, Search, Check, Bot, UserCircle, Settings, Trash2, ChevronDown, ChevronUp } from 'lucide-react';

const GLOW = {
  violet: '0 0 12px rgba(217, 28, 210, 0.5), 0 0 24px rgba(217, 28, 210, 0.2)',
};

// === AI / Human Toggle Switch ===
const AiHumanSwitch = memo(({ isAi, onToggle, size = 'normal' }) => {
  const h = size === 'small' ? 28 : 36;
  const w = size === 'small' ? 64 : 80;
  const dot = size === 'small' ? 20 : 28;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <span style={{
        fontSize: size === 'small' ? '11px' : '12px',
        color: !isAi ? '#D91CD2' : 'rgba(255,255,255,0.35)',
        fontWeight: !isAi ? '700' : '500',
        transition: 'all 0.2s',
      }}>
        <UserCircle size={size === 'small' ? 12 : 14} style={{ marginRight: '3px', verticalAlign: 'middle' }} />
        Humain
      </span>
      <button
        onClick={onToggle}
        style={{
          width: `${w}px`, height: `${h}px`, borderRadius: `${h}px`,
          background: isAi
            ? 'linear-gradient(135deg, #D91CD2, #8b5cf6)'
            : 'rgba(255,255,255,0.12)',
          border: 'none', cursor: 'pointer', position: 'relative',
          transition: 'all 0.3s ease',
          boxShadow: isAi ? '0 0 12px rgba(217,28,210,0.3)' : 'none',
        }}
      >
        <div style={{
          width: `${dot}px`, height: `${dot}px`, borderRadius: '50%',
          background: '#fff',
          position: 'absolute',
          top: '50%', transform: 'translateY(-50%)',
          left: isAi ? `${w - dot - 4}px` : '4px',
          transition: 'left 0.3s ease',
          boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          {isAi ? <Bot size={size === 'small' ? 10 : 14} color="#D91CD2" /> : <UserCircle size={size === 'small' ? 10 : 14} color="#666" />}
        </div>
      </button>
      <span style={{
        fontSize: size === 'small' ? '11px' : '12px',
        color: isAi ? '#D91CD2' : 'rgba(255,255,255,0.35)',
        fontWeight: isAi ? '700' : '500',
        transition: 'all 0.2s',
      }}>
        <Bot size={size === 'small' ? 12 : 14} style={{ marginRight: '3px', verticalAlign: 'middle' }} />
        IA
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
    return (c.name || '').toLowerCase().includes(q) ||
           (c.email || '').toLowerCase().includes(q) ||
           (c.whatsapp || '').toLowerCase().includes(q);
  });

  return (
    <div style={{
      background: 'rgba(255,255,255,0.02)',
      border: '1px solid rgba(255,255,255,0.06)',
      borderRadius: '12px', overflow: 'hidden',
    }}>
      {/* Search */}
      <div style={{
        padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.04)',
        display: 'flex', alignItems: 'center', gap: '8px',
      }}>
        <Search size={14} color="rgba(255,255,255,0.3)" />
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Rechercher un membre..."
          style={{
            flex: 1, background: 'none', border: 'none',
            color: '#fff', fontSize: '12px', outline: 'none',
          }}
        />
        {selectedIds.size > 0 && (
          <span style={{
            padding: '2px 8px', borderRadius: '10px',
            background: 'rgba(217,28,210,0.15)', color: '#D91CD2',
            fontSize: '10px', fontWeight: '700',
          }}>
            {selectedIds.size}
          </span>
        )}
      </div>

      {/* Members list */}
      <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
        {filtered.length === 0 ? (
          <p style={{ padding: '16px', textAlign: 'center', color: 'rgba(255,255,255,0.25)', fontSize: '12px', margin: 0 }}>
            Aucun contact trouvé
          </p>
        ) : filtered.map(contact => {
          const cid = contact.id || contact.email || contact.whatsapp;
          const isSelected = selectedIds.has(cid);
          return (
            <button
              key={cid}
              onClick={() => onToggleMember(cid)}
              style={{
                width: '100%', padding: '10px 12px',
                display: 'flex', alignItems: 'center', gap: '10px',
                background: isSelected ? 'rgba(217,28,210,0.06)' : 'transparent',
                border: 'none', borderBottom: '1px solid rgba(255,255,255,0.03)',
                cursor: 'pointer', textAlign: 'left',
                transition: 'background 0.15s',
              }}
            >
              {/* Avatar */}
              <div style={{
                width: '32px', height: '32px', borderRadius: '50%',
                background: isSelected ? 'linear-gradient(135deg, #D91CD2, #8b5cf6)' : 'rgba(255,255,255,0.08)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#fff', fontSize: '12px', fontWeight: '700',
                border: isSelected ? '2px solid #D91CD2' : '2px solid transparent',
                transition: 'all 0.2s',
              }}>
                {isSelected ? <Check size={14} /> : (contact.name || '?')[0].toUpperCase()}
              </div>
              <div style={{ flex: 1 }}>
                <p style={{ color: '#fff', fontSize: '12px', fontWeight: '600', margin: 0 }}>
                  {contact.name || 'Sans nom'}
                </p>
                <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: '10px', margin: '2px 0 0' }}>
                  {contact.email || contact.whatsapp || ''}
                </p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
});
MemberSelector.displayName = 'MemberSelector';

// === Group Card ===
const GroupCard = memo(({ group, onSelect, onDelete, isActive }) => {
  const memberCount = (group.members || []).length;

  return (
    <button
      onClick={() => onSelect(group)}
      style={{
        width: '100%', padding: '12px', borderRadius: '12px',
        background: isActive ? 'rgba(217,28,210,0.08)' : '#1A1A1A',
        border: isActive ? '1px solid rgba(217,28,210,0.3)' : '1px solid rgba(255,255,255,0.06)',
        cursor: 'pointer', textAlign: 'left',
        display: 'flex', alignItems: 'center', gap: '12px',
        transition: 'all 0.2s',
      }}
    >
      <div style={{
        width: '40px', height: '40px', borderRadius: '12px',
        background: 'linear-gradient(135deg, rgba(217,28,210,0.15), rgba(139,92,246,0.1))',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Users size={18} color="#D91CD2" />
      </div>
      <div style={{ flex: 1 }}>
        <p style={{ color: '#fff', fontSize: '13px', fontWeight: '600', margin: 0 }}>
          {group.name || 'Groupe sans nom'}
        </p>
        <p style={{ color: 'rgba(255,255,255,0.35)', fontSize: '10px', margin: '2px 0 0' }}>
          {memberCount} membre{memberCount > 1 ? 's' : ''} • {group.is_ai_active ? '🤖 IA' : '👤 Humain'}
        </p>
      </div>
      <button
        onClick={e => { e.stopPropagation(); onDelete(group.id); }}
        style={{
          background: 'none', border: 'none', color: 'rgba(239,68,68,0.4)',
          cursor: 'pointer', padding: '4px',
        }}
      >
        <Trash2 size={14} />
      </button>
    </button>
  );
});
GroupCard.displayName = 'GroupCard';

// === Main GroupChatModule ===
const GroupChatModule = memo(({
  groups = [],
  contacts = [],
  activeGroupId,
  onCreateGroup,
  onDeleteGroup,
  onSelectGroup,
  onToggleAi,
}) => {
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [selectedMembers, setSelectedMembers] = useState(new Set());
  const [isAiActive, setIsAiActive] = useState(true);
  const [expanded, setExpanded] = useState(true);

  const toggleMember = useCallback((memberId) => {
    setSelectedMembers(prev => {
      const next = new Set(prev);
      if (next.has(memberId)) next.delete(memberId); else next.add(memberId);
      return next;
    });
  }, []);

  const handleCreate = async () => {
    if (!newGroupName.trim()) return;
    await onCreateGroup({
      name: newGroupName.trim(),
      members: Array.from(selectedMembers),
      is_ai_active: isAiActive,
    });
    setNewGroupName('');
    setSelectedMembers(new Set());
    setIsAiActive(true);
    setShowCreateForm(false);
  };

  return (
    <div style={{
      background: '#1A1A1A',
      border: '1px solid rgba(255,255,255,0.06)',
      borderRadius: '16px', overflow: 'hidden',
    }}>
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          width: '100%', padding: '14px 16px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: 'none', border: 'none', cursor: 'pointer',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            width: '28px', height: '28px', borderRadius: '8px',
            background: 'linear-gradient(135deg, #D91CD2, #9333ea)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Users size={14} color="#fff" />
          </div>
          <span style={{ color: '#fff', fontSize: '14px', fontWeight: '700' }}>
            Groupes ({groups.length})
          </span>
        </div>
        {expanded ? <ChevronUp size={16} color="rgba(255,255,255,0.3)" /> : <ChevronDown size={16} color="rgba(255,255,255,0.3)" />}
      </button>

      {expanded && (
        <div style={{ padding: '0 16px 16px' }}>
          {/* Groups list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '12px' }}>
            {groups.map(g => (
              <GroupCard
                key={g.id}
                group={g}
                isActive={g.id === activeGroupId}
                onSelect={onSelectGroup}
                onDelete={onDeleteGroup}
              />
            ))}
          </div>

          {/* Create button or form */}
          {!showCreateForm ? (
            <button
              onClick={() => setShowCreateForm(true)}
              style={{
                width: '100%', padding: '10px', borderRadius: '10px',
                background: 'rgba(217,28,210,0.08)',
                border: '1px dashed rgba(217,28,210,0.25)',
                color: '#D91CD2', fontSize: '12px', fontWeight: '600',
                cursor: 'pointer', display: 'flex', alignItems: 'center',
                justifyContent: 'center', gap: '6px',
                transition: 'all 0.2s',
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'rgba(217,28,210,0.15)'}
              onMouseLeave={e => e.currentTarget.style.background = 'rgba(217,28,210,0.08)'}
            >
              <Plus size={14} /> Créer un groupe
            </button>
          ) : (
            <div style={{
              background: 'rgba(217,28,210,0.04)',
              border: '1px solid rgba(217,28,210,0.15)',
              borderRadius: '12px', padding: '14px',
              display: 'flex', flexDirection: 'column', gap: '12px',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: '#D91CD2', fontSize: '12px', fontWeight: '700' }}>
                  Nouveau groupe
                </span>
                <button onClick={() => setShowCreateForm(false)} style={{
                  background: 'none', border: 'none', color: 'rgba(255,255,255,0.3)',
                  cursor: 'pointer', padding: '2px',
                }}>
                  <X size={14} />
                </button>
              </div>

              {/* Group name */}
              <input
                value={newGroupName}
                onChange={e => setNewGroupName(e.target.value)}
                placeholder="Nom du groupe..."
                style={{
                  width: '100%', padding: '10px 12px', borderRadius: '8px',
                  background: 'rgba(255,255,255,0.04)',
                  border: '1px solid rgba(255,255,255,0.08)',
                  color: '#fff', fontSize: '13px', outline: 'none',
                  boxSizing: 'border-box',
                }}
                onFocus={e => e.target.style.borderColor = 'rgba(217,28,210,0.3)'}
                onBlur={e => e.target.style.borderColor = 'rgba(255,255,255,0.08)'}
              />

              {/* AI/Human switch */}
              <div style={{ display: 'flex', justifyContent: 'center' }}>
                <AiHumanSwitch isAi={isAiActive} onToggle={() => setIsAiActive(!isAiActive)} size="small" />
              </div>

              {/* Members */}
              <MemberSelector
                contacts={contacts}
                selectedIds={selectedMembers}
                onToggleMember={toggleMember}
              />

              {/* Create button */}
              <button
                onClick={handleCreate}
                disabled={!newGroupName.trim()}
                style={{
                  padding: '10px', borderRadius: '10px',
                  background: newGroupName.trim() ? 'linear-gradient(135deg, #D91CD2, #9333ea)' : 'rgba(255,255,255,0.06)',
                  border: 'none', color: '#fff', fontSize: '12px', fontWeight: '700',
                  cursor: newGroupName.trim() ? 'pointer' : 'not-allowed',
                  opacity: newGroupName.trim() ? 1 : 0.4,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                }}
              >
                <Plus size={14} /> Créer le groupe
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
});

GroupChatModule.displayName = 'GroupChatModule';
export { AiHumanSwitch, MemberSelector, GroupCard };
export default GroupChatModule;

// CRMSection.js - Section CRM/Conversations v16.3 PREMIUM — V143 Fixes
// Refonte visuelle minimaliste "borderless" — Fond noir profond, accents violet glow
// V143: Message deletion, emoji picker coach, clear mode toggle, reduced system messages
// ANTI-BREAK: Toute la logique data/API est 100% identique à v16.2

import React, { useRef, useCallback, memo, useMemo, useState, useEffect } from 'react';
import axios from 'axios';
import { ChevronDown, Trash2, Send, Copy, Check, ExternalLink, Phone, Edit2, Save, X, MessageCircle, Link2, Users, Bell, Zap, Search, RefreshCw, Bot, UserRound, Wifi, WifiOff } from 'lucide-react';
import SmartLinksSection from './SmartLinksSection'; // v98: Liens Intelligents
import GroupChatModule from './GroupChatModule'; // v100: Groupes de chat
import { renderTextWithLinks } from '../chat/ChatBubbles'; // V156.3: Liens cliquables
import AfricanEmojiPicker from '../chat/AfricanEmojiPicker'; // V143: Emoji picker for coach

// ====== STYLES PREMIUM PARTAGÉS ======
const GLOW = {
  violet: '0 0 12px rgba(217, 28, 210, 0.5), 0 0 24px rgba(217, 28, 210, 0.2)',
  violetSoft: '0 0 8px rgba(217, 28, 210, 0.3)',
  green: '0 0 12px rgba(34, 197, 94, 0.5)',
  red: '0 0 8px rgba(239, 68, 68, 0.4)',
  amber: '0 0 8px rgba(245, 158, 11, 0.4)',
};

const iconBtn = (color, glowColor) => ({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '36px',
  height: '36px',
  borderRadius: '50%',
  background: 'transparent',
  border: 'none',
  color: color,
  cursor: 'pointer',
  transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
});

// ====== COMPOSANT NOTIFICATION BANNER ======
const NotificationBanner = memo(({
  showPermissionBanner,
  notificationPermission,
  setShowPermissionBanner,
  requestNotificationAccess
}) => {
  if (!showPermissionBanner || notificationPermission !== 'default') return null;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '14px 20px',
        background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.12), rgba(217, 28, 210, 0.08))',
        borderBottom: '1px solid rgba(139, 92, 246, 0.15)',
      }}
      data-testid="notification-permission-banner"
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <Bell size={18} style={{ color: '#a78bfa' }} />
        <div>
          <p style={{ color: '#fff', fontSize: '13px', fontWeight: '500', margin: 0 }}>Activez les notifications</p>
          <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px', margin: '2px 0 0' }}>Alerte sonore et visuelle à chaque message.</p>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <button
          onClick={() => setShowPermissionBanner(false)}
          style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.35)', fontSize: '12px', cursor: 'pointer', padding: '6px 10px' }}
        >
          Plus tard
        </button>
        <button
          onClick={requestNotificationAccess}
          style={{
            background: '#22c55e',
            border: 'none',
            borderRadius: '20px',
            color: '#fff',
            fontSize: '12px',
            fontWeight: '600',
            padding: '7px 16px',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
          data-testid="enable-notifications-btn"
        >
          Activer
        </button>
      </div>
    </div>
  );
});
NotificationBanner.displayName = 'NotificationBanner';

// ====== COMPOSANT NOTIFICATION BLOCKED BANNER ======
const NotificationBlockedBanner = memo(({ notificationPermission }) => {
  if (notificationPermission !== 'denied') return null;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '10px 20px',
        borderBottom: '1px solid rgba(239, 68, 68, 0.15)',
      }}
    >
      <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '12px', margin: 0 }}>
        ⚠️ Notifications bloquées — Les alertes apparaîtront ici.
      </p>
      <button
        onClick={() => {
          alert('Pour activer les notifications:\n\n1. Cliquez sur l\'icône 🔒 dans la barre d\'adresse\n2. Trouvez "Notifications"\n3. Changez de "Bloquer" à "Autoriser"\n4. Rafraîchissez la page');
        }}
        style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.35)', fontSize: '11px', cursor: 'pointer', textDecoration: 'underline' }}
      >
        Comment activer ?
      </button>
    </div>
  );
});
NotificationBlockedBanner.displayName = 'NotificationBlockedBanner';

// ====== COMPOSANT TOAST NOTIFICATIONS ======
const ToastNotifications = memo(({ toastNotifications, handleToastClick, dismissToast }) => {
  if (toastNotifications.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 max-w-sm" data-testid="notification-toasts">
      {toastNotifications.map(toast => (
        <div
          key={toast.id}
          onClick={() => handleToastClick(toast)}
          style={{
            background: 'rgba(15, 15, 15, 0.95)',
            backdropFilter: 'blur(20px)',
            borderRadius: '16px',
            padding: '14px 18px',
            cursor: 'pointer',
            boxShadow: GLOW.violet,
            borderLeft: '3px solid #D91CD2',
            transition: 'transform 0.2s',
          }}
          data-testid={`toast-${toast.id}`}
        >
          <div style={{ display: 'flex', alignItems: 'start', justifyContent: 'space-between', gap: '12px' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ color: '#D91CD2', fontWeight: '600', fontSize: '13px', margin: 0 }}>
                {toast.senderName}
              </p>
              <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: '12px', marginTop: '4px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {toast.content.substring(0, 60)}{toast.content.length > 60 ? '…' : ''}
              </p>
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); dismissToast(toast.id); }}
              style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.3)', cursor: 'pointer', padding: '2px', fontSize: '14px' }}
            >
              ✕
            </button>
          </div>
        </div>
      ))}
    </div>
  );
});
ToastNotifications.displayName = 'ToastNotifications';

// ====== COMPOSANT NOTIFICATION TEST ======
const NotificationTestPanel = memo(({
  notificationPermission,
  handleTestNotification,
  notifyOnAiResponse,
  toggleNotifyOnAiResponse
}) => (
  <div style={{
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 20px',
    borderBottom: '1px solid rgba(255,255,255,0.05)',
  }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
      <Bell size={16} style={{ color: 'rgba(255,255,255,0.3)' }} />
      <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '12px' }}>
        {notificationPermission === 'granted' ? '✅ Notifications actives' :
         notificationPermission === 'denied' ? '⚠️ Bloquées' :
         '🔔 En attente'}
      </span>
    </div>
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
      <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
        <input
          type="checkbox"
          checked={notifyOnAiResponse}
          onChange={toggleNotifyOnAiResponse}
          style={{ accentColor: '#D91CD2', width: '14px', height: '14px' }}
        />
        <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px' }}>Notif IA</span>
      </label>
      <button
        onClick={handleTestNotification}
        style={{
          background: 'none',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: '20px',
          color: 'rgba(255,255,255,0.5)',
          fontSize: '11px',
          padding: '5px 12px',
          cursor: 'pointer',
          transition: 'all 0.2s',
        }}
        data-testid="test-notification-btn"
      >
        Tester
      </button>
    </div>
  </div>
));
NotificationTestPanel.displayName = 'NotificationTestPanel';

// ====== COMPOSANT GENERATE LINK CARD — PREMIUM BORDERLESS ======
const GenerateLinkCard = memo(({
  newLinkTitle,
  setNewLinkTitle,
  newLinkCustomPrompt,
  setNewLinkCustomPrompt,
  generateShareableLink,
  loadingConversations,
  isSuperAdmin,
  enhancePromptWithAI
}) => {
  const [isEnhancing, setIsEnhancing] = React.useState(false);
  const textareaRef = useRef(null);

  const handleEnhancePrompt = async () => {
    if (!newLinkCustomPrompt.trim() || isEnhancing) return;
    setIsEnhancing(true);
    try {
      const enhanced = await enhancePromptWithAI(newLinkCustomPrompt);
      if (enhanced) {
        setNewLinkCustomPrompt(enhanced);
      }
    } catch (err) {
      console.error('Erreur amélioration prompt:', err);
    }
    setIsEnhancing(false);
  };

  // Auto-expand textarea
  const handlePromptChange = (e) => {
    setNewLinkCustomPrompt(e.target.value);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px';
    }
  };

  return (
    <div style={{ padding: '24px 20px', borderBottom: '1px solid rgba(217, 28, 210, 0.1)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
        <div style={{
          width: '32px', height: '32px', borderRadius: '50%',
          background: 'rgba(217, 28, 210, 0.12)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Link2 size={16} style={{ color: '#D91CD2' }} />
        </div>
        <span style={{ color: '#fff', fontSize: '15px', fontWeight: '600', letterSpacing: '-0.01em' }}>
          Nouveau lien de chat
        </span>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'flex-end' }}>
        <div style={{ flex: '1 1 200px' }}>
          <label style={{ display: 'block', fontSize: '11px', color: 'rgba(255,255,255,0.3)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Titre</label>
          <input
            type="text"
            value={newLinkTitle}
            onChange={(e) => setNewLinkTitle(e.target.value)}
            placeholder="Ex: Offre Janvier"
            style={{
              width: '100%',
              padding: '10px 14px',
              background: 'rgba(255,255,255,0.04)',
              border: 'none',
              borderBottom: '1px solid rgba(255,255,255,0.08)',
              borderRadius: '0',
              color: '#fff',
              fontSize: '14px',
              outline: 'none',
              transition: 'border-color 0.2s',
            }}
            onFocus={(e) => e.target.style.borderBottomColor = '#D91CD2'}
            onBlur={(e) => e.target.style.borderBottomColor = 'rgba(255,255,255,0.08)'}
            data-testid="link-title-input"
          />
        </div>

        {isSuperAdmin && (
          <div style={{ flex: '1 1 200px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
              <label style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Prompt IA</label>
              <button
                onClick={handleEnhancePrompt}
                disabled={isEnhancing || !newLinkCustomPrompt.trim()}
                style={{
                  background: 'none',
                  border: 'none',
                  color: isEnhancing ? 'rgba(255,255,255,0.3)' : '#f59e0b',
                  fontSize: '13px',
                  cursor: isEnhancing ? 'wait' : 'pointer',
                  padding: '2px 6px',
                  opacity: !newLinkCustomPrompt.trim() ? 0.3 : 1,
                }}
                title="Améliorer avec l'IA"
                data-testid="enhance-prompt-btn"
              >
                {isEnhancing ? '⏳' : '✨ Améliorer'}
              </button>
            </div>
            <textarea
              ref={textareaRef}
              value={newLinkCustomPrompt}
              onChange={handlePromptChange}
              placeholder="Décrivez le comportement souhaité de l'IA…"
              rows={1}
              style={{
                width: '100%',
                padding: '10px 14px',
                background: 'rgba(255,255,255,0.04)',
                border: 'none',
                borderBottom: '1px solid rgba(255,255,255,0.08)',
                borderRadius: '0',
                color: '#fff',
                fontSize: '14px',
                outline: 'none',
                resize: 'none',
                overflow: 'hidden',
                minHeight: '40px',
                fontFamily: 'inherit',
                transition: 'border-color 0.2s',
              }}
              onFocus={(e) => e.target.style.borderBottomColor = '#D91CD2'}
              onBlur={(e) => e.target.style.borderBottomColor = 'rgba(255,255,255,0.08)'}
              data-testid="link-prompt-input"
            />
          </div>
        )}

        <button
          onClick={generateShareableLink}
          disabled={loadingConversations}
          style={{
            padding: '10px 24px',
            background: '#D91CD2',
            border: 'none',
            borderRadius: '24px',
            color: '#fff',
            fontSize: '13px',
            fontWeight: '600',
            cursor: loadingConversations ? 'wait' : 'pointer',
            opacity: loadingConversations ? 0.5 : 1,
            transition: 'all 0.25s',
            boxShadow: 'none',
            whiteSpace: 'nowrap',
          }}
          onMouseEnter={(e) => { if (!loadingConversations) e.target.style.boxShadow = GLOW.violet; }}
          onMouseLeave={(e) => e.target.style.boxShadow = 'none'}
          data-testid="generate-link-btn"
        >
          {loadingConversations ? '⏳' : '+ Créer'}
        </button>
      </div>
    </div>
  );
});
GenerateLinkCard.displayName = 'GenerateLinkCard';

// v105: CommunityCard SUPPRIMÉ — tout passe par GroupChatModule + Conversations Directes

// ====== COMPOSANT LINK ITEM — PREMIUM BORDERLESS (v16.2) ======
const LinkItem = memo(({ link, copiedLinkId, copyLinkToClipboard, deleteChatLink, updateChatLink }) => {
  const linkToken = link.link_token || link.token || '';
  const customPrompt = link.custom_prompt || link.customPrompt || '';
  const createdAt = link.created_at || link.createdAt || '';
  const usageCount = link.participant_count || link.usageCount || 0;
  const fullUrl = `${window.location.origin}/?link=${linkToken}`;
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(link.title || '');
  const [editPrompt, setEditPrompt] = useState(customPrompt);
  const [saving, setSaving] = useState(false);
  const editTextareaRef = useRef(null);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateChatLink(link.id, { title: editTitle, custom_prompt: editPrompt || null });
      setIsEditing(false);
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  // Auto-expand edit textarea
  const handleEditPromptChange = (e) => {
    setEditPrompt(e.target.value);
    if (editTextareaRef.current) {
      editTextareaRef.current.style.height = 'auto';
      editTextareaRef.current.style.height = editTextareaRef.current.scrollHeight + 'px';
    }
  };

  if (isEditing) {
    return (
      <div style={{
        padding: '16px 0',
        borderBottom: '1px solid rgba(139, 92, 246, 0.15)',
      }}>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', fontSize: '10px', color: 'rgba(255,255,255,0.3)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Titre</label>
          <input
            value={editTitle}
            onChange={e => setEditTitle(e.target.value)}
            style={{
              width: '100%',
              padding: '8px 0',
              background: 'transparent',
              border: 'none',
              borderBottom: '1px solid rgba(139, 92, 246, 0.3)',
              color: '#fff',
              fontSize: '14px',
              outline: 'none',
            }}
            placeholder="Ex: Regime Camerounais"
          />
        </div>
        <div style={{ marginBottom: '14px' }}>
          <label style={{ display: 'block', fontSize: '10px', color: 'rgba(255,255,255,0.3)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Prompt IA</label>
          <textarea
            ref={editTextareaRef}
            value={editPrompt}
            onChange={handleEditPromptChange}
            rows={2}
            style={{
              width: '100%',
              padding: '8px 0',
              background: 'transparent',
              border: 'none',
              borderBottom: '1px solid rgba(139, 92, 246, 0.3)',
              color: '#fff',
              fontSize: '13px',
              outline: 'none',
              resize: 'none',
              overflow: 'hidden',
              minHeight: '36px',
              fontFamily: 'inherit',
            }}
            placeholder="Ex: Tu es un expert diététicien…"
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
          <button
            onClick={() => setIsEditing(false)}
            style={{
              background: 'none',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '20px',
              color: 'rgba(255,255,255,0.5)',
              fontSize: '12px',
              padding: '6px 14px',
              cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '4px',
            }}
          >
            <X size={12} /> Annuler
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              background: '#8b5cf6',
              border: 'none',
              borderRadius: '20px',
              color: '#fff',
              fontSize: '12px',
              fontWeight: '600',
              padding: '6px 16px',
              cursor: saving ? 'wait' : 'pointer',
              opacity: saving ? 0.5 : 1,
              display: 'flex', alignItems: 'center', gap: '4px',
            }}
          >
            <Save size={12} /> {saving ? '…' : 'Sauver'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        padding: '14px 0',
        borderBottom: '1px solid rgba(255,255,255,0.04)',
        transition: 'background 0.2s',
      }}
      data-testid={`link-item-${link.id}`}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ color: '#fff', fontSize: '14px', fontWeight: '500', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {link.title || 'Lien sans titre'}
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '4px' }}>
            <span style={{ color: 'rgba(255,255,255,0.25)', fontSize: '11px' }}>{usageCount} util.</span>
            <span style={{ color: 'rgba(255,255,255,0.25)', fontSize: '11px' }}>
              {(() => {
                try {
                  const d = new Date(createdAt);
                  return isNaN(d.getTime()) ? '—' : new Intl.DateTimeFormat('fr-CH', { dateStyle: 'short' }).format(d);
                } catch { return '—'; }
              })()}
            </span>
          </div>
        </div>

        {/* Actions icônes avec glow */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginLeft: '12px' }}>
          {[
            { icon: Edit2, color: '#f59e0b', glow: GLOW.amber, title: 'Modifier', onClick: () => { setEditTitle(link.title || ''); setEditPrompt(customPrompt); setIsEditing(true); } },
            { icon: copiedLinkId === link.id ? Check : Copy, color: '#a78bfa', glow: GLOW.violetSoft, title: 'Copier', onClick: () => copyLinkToClipboard(linkToken), testId: `copy-link-${link.id}` },
            { icon: ExternalLink, color: '#22c55e', glow: GLOW.green, title: 'Ouvrir', isLink: true, href: fullUrl },
            { icon: Trash2, color: '#ef4444', glow: GLOW.red, title: 'Supprimer', onClick: () => deleteChatLink(link.id), testId: `delete-link-${link.id}` },
          ].map((action, i) => {
            const Icon = action.icon;
            if (action.isLink) {
              return (
                <a
                  key={i}
                  href={action.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={iconBtn(action.color, action.glow)}
                  title={action.title}
                  onMouseEnter={(e) => e.currentTarget.style.boxShadow = action.glow}
                  onMouseLeave={(e) => e.currentTarget.style.boxShadow = 'none'}
                >
                  <Icon size={15} />
                </a>
              );
            }
            return (
              <button
                key={i}
                onClick={action.onClick}
                style={iconBtn(action.color, action.glow)}
                title={action.title}
                data-testid={action.testId}
                onMouseEnter={(e) => e.currentTarget.style.boxShadow = action.glow}
                onMouseLeave={(e) => e.currentTarget.style.boxShadow = 'none'}
              >
                <Icon size={15} />
              </button>
            );
          })}
        </div>
      </div>

      {/* Prompt badge — subtle */}
      {customPrompt && (
        <p style={{
          margin: '8px 0 0',
          padding: '0',
          color: 'rgba(167, 139, 250, 0.6)',
          fontSize: '11px',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          ✦ {customPrompt}
        </p>
      )}
    </div>
  );
});
LinkItem.displayName = 'LinkItem';

// ====== COMPOSANT CHAT LINKS LIST — PREMIUM BORDERLESS ======
const ChatLinksList = memo(({ chatLinks, copiedLinkId, copyLinkToClipboard, deleteChatLink, updateChatLink }) => {
  if (chatLinks.length === 0) return null;

  return (
    <div style={{ padding: '0 20px 20px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
        <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: '600' }}>
          Liens actifs
        </span>
        <span style={{
          background: 'rgba(217, 28, 210, 0.15)',
          color: '#D91CD2',
          fontSize: '10px',
          fontWeight: '700',
          padding: '2px 8px',
          borderRadius: '10px',
        }}>
          {chatLinks.length}
        </span>
      </div>
      <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
        {chatLinks.map(link => (
          <LinkItem
            key={link.id}
            link={link}
            copiedLinkId={copiedLinkId}
            copyLinkToClipboard={copyLinkToClipboard}
            deleteChatLink={deleteChatLink}
            updateChatLink={updateChatLink}
          />
        ))}
      </div>
    </div>
  );
});
ChatLinksList.displayName = 'ChatLinksList';

// ====== COMPOSANT CONVERSATION ITEM — PREMIUM BORDERLESS ======
const ConversationItem = memo(({
  session,
  selectedSession,
  setSelectedSession,
  loadSessionMessages,
  setSessionMode,
  deleteChatSession,
  isSuperAdmin,
  bulkMode,
  bulkSelected,
  toggleBulkSelect
}) => {
  const isSelected = selectedSession?.id === session.id;
  const hasUnread = session.unreadCount > 0;
  const isBulkChecked = bulkSelected?.has(session.id);

  return (
    <div
      onClick={() => {
        if (bulkMode) { toggleBulkSelect(session.id); return; }
        setSelectedSession(session);
        loadSessionMessages(session.id);
      }}
      style={{
        padding: '10px 10px',
        borderRadius: '12px',
        cursor: 'pointer',
        transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
        background: isBulkChecked ? 'rgba(239,68,68,0.08)' : isSelected ? 'rgba(217, 28, 210, 0.12)' : 'rgba(255,255,255,0.02)',
        borderLeft: isBulkChecked ? '2px solid #ef4444' : isSelected ? '2px solid #D91CD2' : '2px solid transparent',
        border: isSelected ? '1px solid rgba(217, 28, 210, 0.25)' : '1px solid rgba(255,255,255,0.04)',
        borderLeftWidth: isBulkChecked || isSelected ? '2px' : '2px',
        borderLeftColor: isBulkChecked ? '#ef4444' : isSelected ? '#D91CD2' : 'transparent',
        boxShadow: isSelected ? '0 0 15px rgba(217, 28, 210, 0.08), inset 0 0 20px rgba(217, 28, 210, 0.03)' : 'none',
        marginBottom: '4px',
        overflow: 'hidden',
      }}
      onMouseEnter={(e) => { if (!isSelected && !isBulkChecked) { e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; e.currentTarget.style.borderColor = 'rgba(217, 28, 210, 0.15)'; e.currentTarget.style.boxShadow = '0 0 10px rgba(217, 28, 210, 0.05)'; }}}
      onMouseLeave={(e) => { if (!isSelected && !isBulkChecked) { e.currentTarget.style.background = 'rgba(255,255,255,0.02)'; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.04)'; e.currentTarget.style.boxShadow = 'none'; }}}
      data-testid={`conversation-${session.id}`}
    >
      <div style={{ display: 'flex', alignItems: 'start', justifyContent: 'space-between', gap: '8px', overflow: 'hidden' }}>
        {/* v38: Checkbox bulk select */}
        {bulkMode && (
          <div
            onClick={(e) => { e.stopPropagation(); toggleBulkSelect(session.id); }}
            style={{
              width: '22px', height: '22px', minWidth: '22px', borderRadius: '6px',
              border: isBulkChecked ? '2px solid #ef4444' : '2px solid rgba(255,255,255,0.2)',
              background: isBulkChecked ? '#ef4444' : 'transparent',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: 'pointer', transition: 'all 0.2s ease', marginTop: '2px',
              boxShadow: isBulkChecked ? '0 0 8px rgba(239,68,68,0.4)' : 'none'
            }}
          >
            {isBulkChecked && <Check size={14} style={{ color: '#fff', strokeWidth: 3 }} />}
          </div>
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {/* V144: Mode indicator dot — handles bot/ai/human modes */}
            <div style={{
              width: '8px', height: '8px', borderRadius: '50%',
              background: (session.mode === 'bot' || session.mode === 'ai' || session.is_ai_active) ? '#8b5cf6' : '#f59e0b',
              flexShrink: 0,
              boxShadow: (session.mode === 'bot' || session.mode === 'ai' || session.is_ai_active) ? '0 0 6px rgba(139,92,246,0.5)' : '0 0 6px rgba(245,158,11,0.5)',
            }} />
            <p style={{ color: '#fff', fontSize: '13px', fontWeight: '500', margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {session.participantName || session.participantEmail || 'Client'}
            </p>
            {hasUnread && (
              <span style={{
                background: '#D91CD2',
                color: '#fff',
                fontSize: '10px',
                fontWeight: '700',
                padding: '1px 6px',
                borderRadius: '8px',
                flexShrink: 0,
              }}>
                {session.unreadCount}
              </span>
            )}
          </div>

          <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '12px', margin: '4px 0 0 16px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {session.lastMessage || 'Nouvelle conversation'}
          </p>

          {/* V144: WhatsApp + Email — compact, truncated on mobile */}
          <div style={{ marginLeft: '16px', marginTop: '4px', display: 'flex', flexWrap: 'wrap', gap: '6px', overflow: 'hidden' }}>
            {session.participantWhatsapp && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  const phone = session.participantWhatsapp.replace(/[\s\-()]/g, '');
                  window.open(`https://wa.me/${phone.replace('+', '')}`, '_blank');
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'rgba(34, 197, 94, 0.6)',
                  fontSize: '10px',
                  cursor: 'pointer',
                  padding: 0,
                  display: 'flex', alignItems: 'center', gap: '3px',
                  whiteSpace: 'nowrap',
                }}
                title="Contacter sur WhatsApp"
              >
                <Phone size={9} /> {session.participantWhatsapp}
              </button>
            )}
            {session.participantEmail && session.participantEmail !== session.participantName && (
              <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: '10px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '150px' }}>
                {session.participantEmail}
              </span>
            )}
          </div>

          <div style={{ marginLeft: '16px', marginTop: '4px', display: 'flex', gap: '10px' }}>
            <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '10px' }}>
              {(() => {
                try {
                  const dateVal = session.lastActivity || session.createdAt;
                  if (!dateVal) return '—';
                  const d = new Date(dateVal);
                  return isNaN(d.getTime()) ? '—' : d.toLocaleDateString('fr-CH');
                } catch { return '—'; }
              })()}
            </span>
            <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '10px' }}>
              {session.messageCount || 0} msg
            </span>
          </div>
        </div>

        {/* V144: Actions — compact row for mobile, column for desktop */}
        <div className="crm-conv-actions" style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center', flexShrink: 0 }} onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => {
              // V144: mode can be 'bot'|'ai' or 'human' — normalize for setSessionMode
              const isCurrentlyAI = session.mode === 'bot' || session.mode === 'ai' || session.is_ai_active;
              setSessionMode(session.id, isCurrentlyAI ? 'human' : 'ai');
            }}
            style={{
              ...iconBtn((session.mode === 'bot' || session.mode === 'ai' || session.is_ai_active) ? '#8b5cf6' : '#f59e0b'),
              width: '28px', height: '28px',
              background: (session.mode === 'bot' || session.mode === 'ai' || session.is_ai_active) ? 'rgba(139,92,246,0.12)' : 'rgba(245,158,11,0.12)',
              borderRadius: '8px',
            }}
            title={(session.mode === 'bot' || session.mode === 'ai' || session.is_ai_active) ? 'Mode IA — cliquer pour manuel' : 'Manuel — cliquer pour IA'}
          >
            {(session.mode === 'bot' || session.mode === 'ai' || session.is_ai_active) ? <Bot size={12} /> : <UserRound size={12} />}
          </button>
          <button
            onClick={() => deleteChatSession(session.id)}
            style={{ ...iconBtn('rgba(239,68,68,0.6)'), width: '28px', height: '28px' }}
            title="Supprimer"
          >
            <Trash2 size={11} />
          </button>
        </div>
      </div>
    </div>
  );
});
ConversationItem.displayName = 'ConversationItem';

// ====== v16.2: COMPOSANT GROUPED CONVERSATION LIST — PREMIUM ======
const GroupedConversationList = memo(({
  enrichedConversations,
  conversationsListRef,
  handleConversationsScroll,
  selectedSession,
  setSelectedSession,
  loadSessionMessages,
  setSessionMode,
  deleteChatSession,
  isSuperAdmin,
  conversationsHasMore,
  conversationsLoading,
  bulkMode,
  bulkSelected,
  toggleBulkSelect
}) => {
  const [collapsedGroups, setCollapsedGroups] = useState({});

  const grouped = useMemo(() => {
    const groups = {};
    enrichedConversations.forEach(session => {
      const key = session.title || 'Conversations directes';
      if (!groups[key]) groups[key] = [];
      groups[key].push(session);
    });
    return groups;
  }, [enrichedConversations]);

  const groupKeys = Object.keys(grouped);
  const toggleGroup = (key) => {
    setCollapsedGroups(prev => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div
      ref={conversationsListRef}
      onScroll={handleConversationsScroll}
      style={{ maxHeight: '500px', overflowY: 'auto', paddingRight: '4px', borderRadius: '14px', background: '#1A1A1A', border: '1px solid rgba(217, 28, 210, 0.1)', padding: '8px' }}
    >
      {enrichedConversations.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px 20px' }}>
          <MessageCircle size={32} style={{ color: 'rgba(255,255,255,0.1)', margin: '0 auto 12px' }} />
          <p style={{ color: 'rgba(255,255,255,0.25)', fontSize: '13px', margin: 0 }}>Aucune conversation</p>
        </div>
      ) : (
        groupKeys.map(groupKey => {
          const sessions = grouped[groupKey];
          const isCollapsed = collapsedGroups[groupKey];
          const totalUnread = sessions.reduce((sum, s) => sum + (s.unreadCount || 0), 0);

          return (
            <div key={groupKey} style={{ marginBottom: '8px' }}>
              {/* Group header — minimal */}
              <button
                onClick={() => toggleGroup(groupKey)}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '10px 12px',
                  background: 'rgba(217, 28, 210, 0.04)',
                  border: 'none',
                  borderBottom: isCollapsed ? 'none' : '1px solid rgba(217, 28, 210, 0.12)',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  marginBottom: isCollapsed ? '0' : '6px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <ChevronDown
                    size={12}
                    style={{
                      color: 'rgba(255,255,255,0.25)',
                      transform: isCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)',
                      transition: 'transform 0.2s ease',
                    }}
                  />
                  <span style={{ color: '#D91CD2', fontSize: '12px', fontWeight: '600', textShadow: '0 0 8px rgba(217,28,210,0.3)' }}>
                    {groupKey}
                  </span>
                  <span style={{ color: 'rgba(255,255,255,0.35)', fontSize: '11px' }}>
                    {sessions.length}
                  </span>
                </div>
                {totalUnread > 0 && (
                  <span style={{
                    background: '#D91CD2',
                    color: '#fff',
                    fontSize: '10px',
                    fontWeight: '700',
                    padding: '2px 7px',
                    borderRadius: '8px',
                  }}>
                    {totalUnread}
                  </span>
                )}
              </button>

              {/* Conversations */}
              {!isCollapsed && (
                <div style={{ paddingLeft: '4px' }}>
                  {sessions.map(session => (
                    <ConversationItem
                      key={session.id}
                      session={session}
                      selectedSession={selectedSession}
                      setSelectedSession={setSelectedSession}
                      loadSessionMessages={loadSessionMessages}
                      setSessionMode={setSessionMode}
                      deleteChatSession={deleteChatSession}
                      isSuperAdmin={isSuperAdmin}
                      bulkMode={bulkMode}
                      bulkSelected={bulkSelected}
                      toggleBulkSelect={toggleBulkSelect}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })
      )}
      {conversationsHasMore && (
        <div style={{ textAlign: 'center', padding: '12px', color: 'rgba(255,255,255,0.2)', fontSize: '12px' }}>
          {conversationsLoading ? '⏳' : '↓ Scroll pour plus'}
        </div>
      )}
    </div>
  );
});
GroupedConversationList.displayName = 'GroupedConversationList';

// ====== V107.5: COMPOSANT PROMPT SYSTÈME IA ======
const SystemPromptBlock = memo(({ API, coachEmail }) => {
  const [systemPrompt, setSystemPrompt] = useState('');
  const [savedPrompt, setSavedPrompt] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Charger le prompt existant
  useEffect(() => {
    const load = async () => {
      try {
        const res = await axios.get(`${API}/ai-config`);
        const prompt = res.data?.systemPrompt || '';
        setSystemPrompt(prompt);
        setSavedPrompt(prompt);
      } catch (e) { console.warn('[V107.5] Load prompt:', e); }
      setLoading(false);
    };
    if (API) load();
  }, [API]);

  // Sauvegarder le prompt
  const handleSave = async () => {
    if (!systemPrompt.trim() || saving) return;
    setSaving(true);
    try {
      await axios.put(`${API}/ai-config`, { systemPrompt }, { headers: { 'X-User-Email': coachEmail } });
      setSavedPrompt(systemPrompt);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (e) { console.error('[V107.5] Save prompt:', e); }
    setSaving(false);
  };

  // Générer le Prompt Maître
  const handleGenerate = async () => {
    if (generating) return;
    setGenerating(true);
    try {
      const res = await axios.post(`${API}/ai/generate-master-prompt`, {}, { headers: { 'X-User-Email': coachEmail } });
      if (res.data?.success && res.data?.prompt) {
        setSystemPrompt(res.data.prompt);
        setExpanded(true);
      }
    } catch (e) { console.error('[V107.5] Generate prompt:', e); }
    setGenerating(false);
  };

  const hasChanges = systemPrompt !== savedPrompt;
  const charCount = systemPrompt.length;

  return (
    <div style={{
      margin: '16px 0',
      borderRadius: '16px',
      border: '1px solid rgba(217, 28, 210, 0.1)',
      background: '#111111',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 20px', cursor: 'pointer',
          background: expanded ? 'rgba(217, 28, 210, 0.04)' : 'transparent',
          transition: 'background 0.2s',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Bot size={18} style={{ color: '#D91CD2' }} />
          <span style={{ color: '#fff', fontSize: '14px', fontWeight: '600' }}>Prompt Système IA</span>
          {hasChanges && (
            <span style={{
              fontSize: '10px', color: '#f59e0b', background: 'rgba(245,158,11,0.12)',
              padding: '2px 8px', borderRadius: '10px', fontWeight: '600',
            }}>Non sauvegardé</span>
          )}
          {saveSuccess && (
            <span style={{
              fontSize: '10px', color: '#22c55e', background: 'rgba(34,197,94,0.12)',
              padding: '2px 8px', borderRadius: '10px', fontWeight: '600',
            }}>Sauvegardé</span>
          )}
        </div>
        <ChevronDown size={16} style={{
          color: 'rgba(255,255,255,0.4)',
          transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
          transition: 'transform 0.2s',
        }} />
      </div>

      {/* Body */}
      {expanded && (
        <div style={{ padding: '0 20px 20px' }}>
          <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px', margin: '0 0 12px', lineHeight: '1.5' }}>
            Ce prompt définit le comportement de l'IA dans toutes les conversations. Cliquez sur "Générer Prompt Maître" pour créer automatiquement un prompt basé sur vos cours, offres, articles et infos de la plateforme.
          </p>

          {/* Bouton Générer */}
          <button
            onClick={handleGenerate}
            disabled={generating}
            style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              padding: '10px 20px', marginBottom: '14px',
              borderRadius: '12px', border: 'none',
              background: generating
                ? 'rgba(217, 28, 210, 0.15)'
                : 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
              color: '#fff', fontSize: '13px', fontWeight: '600',
              cursor: generating ? 'wait' : 'pointer',
              boxShadow: generating ? 'none' : GLOW.violet,
              transition: 'all 0.25s',
              width: '100%', justifyContent: 'center',
            }}
            onMouseEnter={(e) => { if (!generating) e.currentTarget.style.boxShadow = '0 0 20px rgba(217, 28, 210, 0.6)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.boxShadow = generating ? 'none' : GLOW.violet; }}
          >
            <Zap size={15} />
            {generating ? 'Génération en cours...' : 'Générer Prompt Maître'}
          </button>

          {/* Textarea */}
          {loading ? (
            <div style={{ color: 'rgba(255,255,255,0.3)', fontSize: '12px', textAlign: 'center', padding: '20px' }}>Chargement...</div>
          ) : (
            <>
              <textarea
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                placeholder="Entrez les instructions système pour l'IA..."
                style={{
                  width: '100%', minHeight: '250px',
                  padding: '14px',
                  background: '#1A1A1A',
                  border: hasChanges ? '1px solid rgba(245, 158, 11, 0.3)' : '1px solid rgba(217, 28, 210, 0.12)',
                  borderRadius: '12px',
                  color: '#fff', fontSize: '13px', lineHeight: '1.6',
                  fontFamily: 'monospace',
                  outline: 'none', resize: 'vertical',
                  transition: 'border-color 0.2s',
                }}
                onFocus={(e) => { e.target.style.borderColor = 'rgba(217, 28, 210, 0.4)'; e.target.style.boxShadow = '0 0 12px rgba(217, 28, 210, 0.08)'; }}
                onBlur={(e) => { e.target.style.borderColor = hasChanges ? 'rgba(245, 158, 11, 0.3)' : 'rgba(217, 28, 210, 0.12)'; e.target.style.boxShadow = 'none'; }}
              />

              {/* Footer: char count + save */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '10px' }}>
                <span style={{ color: 'rgba(255,255,255,0.25)', fontSize: '11px' }}>
                  {charCount} caractères
                </span>
                <button
                  onClick={handleSave}
                  disabled={saving || !hasChanges}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '6px',
                    padding: '8px 18px',
                    borderRadius: '10px', border: 'none',
                    background: !hasChanges ? 'rgba(255,255,255,0.06)' : 'linear-gradient(135deg, #22c55e, #16a34a)',
                    color: !hasChanges ? 'rgba(255,255,255,0.25)' : '#fff',
                    fontSize: '12px', fontWeight: '600',
                    cursor: !hasChanges ? 'default' : 'pointer',
                    boxShadow: hasChanges ? GLOW.green : 'none',
                    transition: 'all 0.25s',
                  }}
                >
                  <Save size={13} />
                  {saving ? 'Sauvegarde...' : 'Sauvegarder'}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
});
SystemPromptBlock.displayName = 'SystemPromptBlock';

// ====== COMPOSANT MAIN CRM SECTION — PREMIUM BORDERLESS ======
const CRMSection = ({
  // Notification state
  showPermissionBanner,
  setShowPermissionBanner,
  notificationPermission,
  requestNotificationAccess,
  toastNotifications,
  handleToastClick,
  dismissToast,
  handleTestNotification,
  notifyOnAiResponse,
  toggleNotifyOnAiResponse,
  // Link generation
  newLinkTitle,
  setNewLinkTitle,
  newLinkCustomPrompt,
  setNewLinkCustomPrompt,
  generateShareableLink,
  enhancePromptWithAI,
  // v105: Community props supprimés
  // Chat links
  chatLinks,
  copiedLinkId,
  copyLinkToClipboard,
  deleteChatLink,
  updateChatLink,
  // Conversations
  enrichedConversations,
  selectedSession,
  setSelectedSession,
  loadSessionMessages,
  setSessionMode,
  deleteChatSession,
  bulkDeleteChatSessions,
  conversationsLoading,
  conversationsHasMore,
  handleConversationsScroll,
  conversationsListRef,
  conversationSearch,
  setConversationSearch,
  loadConversations,
  // Messages
  sessionMessages,
  coachMessage,
  setCoachMessage,
  handleSendMessage,
  // General
  loadingConversations,
  isSuperAdmin,
  API_URL,
  coachEmail = ''
}) => {
  // v38: Bulk selection state
  const [bulkMode, setBulkMode] = useState(false);
  const [bulkSelected, setBulkSelected] = useState(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [rewritingAI, setRewritingAI] = useState(false);
  // V143: Emoji picker for coach + message deletion
  const [showCoachEmojiPicker, setShowCoachEmojiPicker] = useState(false);

  // v105: Réécrire le message avec l'IA — style Afroboost motivant
  const handleRewriteAI = async () => {
    if (!coachMessage.trim() || !API_URL) return;
    setRewritingAI(true);
    try {
      const res = await axios.post(`${API_URL}/ai/enhance-text`, {
        text: coachMessage,
        style: 'afroboost'
      }, { headers: { 'X-User-Email': coachEmail } });
      const enhanced = res.data?.enhanced_text || res.data?.enhanced || res.data?.text || res.data?.result || '';
      if (enhanced) setCoachMessage(enhanced);
    } catch (e) { console.warn('[V105] Réécriture IA:', e); }
    setRewritingAI(false);
  };

  // v104: Contacts unifiés pour GroupChatModule (même source que Contacts + Campagnes)
  const [unifiedContacts, setUnifiedContacts] = useState([]);
  useEffect(() => {
    const loadUnified = async () => {
      try {
        const res = await axios.get(`${API_URL}/contacts/all`, {
          headers: { 'X-User-Email': coachEmail }
        });
        if (res.data?.success) {
          setUnifiedContacts(
            (res.data.contacts || [])
              .filter(c => c.type === 'user')
              .map(c => ({ id: c.id, name: c.name || 'Sans nom', email: c.email || '', whatsapp: c.phone || '' }))
          );
        }
      } catch (e) { console.warn('[CRM] Contacts unifiés:', e); }
    };
    if (API_URL) loadUnified();
  }, [API_URL, coachEmail]);

  // v108: State for new direct conversation dialog
  const [showNewConversationDialog, setShowNewConversationDialog] = useState(false);

  // v105: Real-time polling — refresh conversations every 30s, messages every 15s
  useEffect(() => {
    if (!API_URL) return;
    const convInterval = setInterval(() => {
      if (loadConversations && !conversationsLoading) {
        loadConversations(false);
      }
    }, 30000);
    return () => clearInterval(convInterval);
  }, [API_URL, loadConversations, conversationsLoading]);

  useEffect(() => {
    if (!API_URL || !selectedSession?.id) return;
    const msgInterval = setInterval(() => {
      loadSessionMessages(selectedSession.id);
    }, 15000);
    return () => clearInterval(msgInterval);
  }, [API_URL, selectedSession?.id, loadSessionMessages]);

  const toggleBulkSelect = useCallback((sessionId) => {
    setBulkSelected(prev => {
      const next = new Set(prev);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
  }, []);

  const selectAllConversations = useCallback(() => {
    if (bulkSelected.size === enrichedConversations.length) {
      setBulkSelected(new Set());
    } else {
      setBulkSelected(new Set(enrichedConversations.map(c => c.id)));
    }
  }, [enrichedConversations, bulkSelected.size]);

  const handleBulkDelete = useCallback(async () => {
    if (bulkSelected.size === 0) return;
    if (!window.confirm(`⚠️ Supprimer ${bulkSelected.size} conversation${bulkSelected.size > 1 ? 's' : ''} ?\n\nCette action est irréversible.`)) return;
    setBulkDeleting(true);
    try {
      await bulkDeleteChatSessions([...bulkSelected]);
      setBulkSelected(new Set());
      setBulkMode(false);
    } catch (err) {
      console.error('Bulk delete error:', err);
    }
    setBulkDeleting(false);
  }, [bulkSelected, bulkDeleteChatSessions]);

  const exitBulkMode = useCallback(() => {
    setBulkMode(false);
    setBulkSelected(new Set());
  }, []);

  // v108: Create a new direct conversation with a participant
  const createDirectConversation = useCallback(async (participantId, participantEmail, participantName) => {
    if (!API_URL || !participantId) return;
    try {
      const sessionData = {
        mode: 'ai',
        is_ai_active: true,
        title: `${participantName || participantEmail || 'Conversation'}`,
        participant_ids: [participantId],
      };
      const res = await axios.post(`${API_URL}/chat/sessions`, sessionData, {
        headers: { 'X-User-Email': coachEmail }
      });
      if (res.data?.id) {
        // Load the new session
        const newSession = res.data;
        await loadSessionMessages(newSession.id);
        // Reload conversations to show the new one
        if (loadConversations) await loadConversations(false);
        // Select the new session
        setSelectedSession(newSession);
      }
    } catch (e) {
      console.error('[V108] Erreur création conversation directe:', e);
      alert('Erreur lors de la création de la conversation');
    }
  }, [API_URL, coachEmail, loadSessionMessages, loadConversations, setSelectedSession]);

  // v108: Toggle AI/Human mode for the selected conversation
  const handleToggleSelectedSessionAI = useCallback(async () => {
    if (!selectedSession?.id || !API_URL) return;
    try {
      const res = await axios.post(`${API_URL}/chat/sessions/${selectedSession.id}/toggle-ai`, {}, {
        headers: { 'X-User-Email': coachEmail }
      });
      if (res.data?.id) {
        setSelectedSession(res.data);
      }
    } catch (e) {
      console.error('[V108] Erreur toggle IA:', e);
    }
  }, [selectedSession?.id, API_URL, coachEmail, setSelectedSession]);

  // V143: Delete individual message (soft delete via API)
  const handleDeleteMessage = useCallback(async (messageId) => {
    if (!messageId || !API_URL) return;
    try {
      await axios.put(`${API_URL}/chat/messages/${messageId}/delete`);
      // Update local sessionMessages state — but sessionMessages comes from parent
      // We need to trigger a reload of messages
      if (selectedSession?.id) {
        loadSessionMessages(selectedSession.id);
      }
    } catch (e) {
      console.error('[V143] Erreur suppression message:', e);
    }
  }, [API_URL, selectedSession?.id, loadSessionMessages]);

  return (
    <div style={{ background: '#000000', borderRadius: '20px', overflow: 'hidden', width: '100%', maxWidth: '100%', boxSizing: 'border-box' }}>
      {/* v108: Modal for creating a new direct conversation */}
      {showNewConversationDialog && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 1000, backdropFilter: 'blur(4px)',
        }} onClick={() => setShowNewConversationDialog(false)}>
          <div style={{
            background: '#111111', border: '1px solid rgba(217,28,210,0.2)', borderRadius: '16px',
            padding: '20px', width: '90%', maxWidth: '500px', maxHeight: '80vh', overflowY: 'auto',
            boxShadow: '0 10px 40px rgba(217,28,210,0.2)',
          }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <h3 style={{ color: '#fff', fontSize: '16px', fontWeight: '700', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                <MessageCircle size={18} style={{ color: '#D91CD2' }} />
                Nouvelle conversation
              </h3>
              <button onClick={() => setShowNewConversationDialog(false)} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', cursor: 'pointer', fontSize: '20px', padding: '0' }}>
                ×
              </button>
            </div>

            {unifiedContacts.length === 0 ? (
              <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: '13px', textAlign: 'center', padding: '20px' }}>
                Aucun contact disponible
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {unifiedContacts.map(contact => (
                  <button
                    key={contact.id || contact.email}
                    onClick={() => {
                      createDirectConversation(contact.id || contact.email, contact.email, contact.name);
                      setShowNewConversationDialog(false);
                    }}
                    style={{
                      padding: '12px 14px', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(217,28,210,0.15)',
                      borderRadius: '10px', cursor: 'pointer', textAlign: 'left', transition: 'all 0.2s',
                      display: 'flex', alignItems: 'center', gap: '10px',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = 'rgba(217,28,210,0.1)';
                      e.currentTarget.style.borderColor = 'rgba(217,28,210,0.3)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
                      e.currentTarget.style.borderColor = 'rgba(217,28,210,0.15)';
                    }}
                  >
                    <div style={{
                      width: '36px', height: '36px', borderRadius: '50%',
                      background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)', display: 'flex',
                      alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: '13px', fontWeight: '700', flexShrink: 0,
                    }}>
                      {(contact.name || contact.email || '?')[0].toUpperCase()}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ color: '#fff', fontSize: '13px', fontWeight: '600', margin: 0 }}>
                        {contact.name || 'Sans nom'}
                      </p>
                      <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: '11px', margin: '2px 0 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {contact.email || contact.whatsapp || '—'}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
      {/* Banner Permission */}
      <NotificationBanner
        showPermissionBanner={showPermissionBanner}
        notificationPermission={notificationPermission}
        setShowPermissionBanner={setShowPermissionBanner}
        requestNotificationAccess={requestNotificationAccess}
      />

      {/* Banner Blocked */}
      <NotificationBlockedBanner notificationPermission={notificationPermission} />

      {/* Toast Notifications */}
      <ToastNotifications
        toastNotifications={toastNotifications}
        handleToastClick={handleToastClick}
        dismissToast={dismissToast}
      />

      {/* Notification Test — discret */}
      <NotificationTestPanel
        notificationPermission={notificationPermission}
        handleTestNotification={handleTestNotification}
        notifyOnAiResponse={notifyOnAiResponse}
        toggleNotifyOnAiResponse={toggleNotifyOnAiResponse}
      />

      {/* v98: Liens Intelligents — remplace GenerateLinkCard + ChatLinksList */}
      <SmartLinksSection
        chatLinks={chatLinks}
        copiedLinkId={copiedLinkId}
        copyLinkToClipboard={copyLinkToClipboard}
        deleteChatLink={deleteChatLink}
        updateChatLink={updateChatLink}
        generateShareableLink={generateShareableLink}
        loadingConversations={loadingConversations}
        API={API_URL}
        coachEmail={coachEmail}
      />

      {/* v105: Communauté supprimée — tout passe par GroupChatModule */}

      {/* v107.5: Prompt Système IA */}
      <SystemPromptBlock API={API_URL} coachEmail={coachEmail} />

      {/* v104: Module Groupes de Chat — contacts unifiés (même source que Contacts + Campagnes) */}
      <GroupChatModule
        contacts={unifiedContacts}
        API={API_URL}
        coachEmail={coachEmail}
      />

      {/* V145: Global mobile CSS + Conversations Grid */}
      <style>{`
        .crm-root, .crm-root * { box-sizing: border-box; }
        .crm-root { width: 100%; max-width: 100%; overflow: hidden; }
        @media (min-width: 1024px) {
          .crm-grid-premium { grid-template-columns: 1fr 1fr !important; }
        }
        @media (max-width: 768px) {
          .crm-conv-list { padding: 8px 4px !important; }
          .crm-msg-detail { padding: 8px 4px !important; min-height: 300px !important; }
          .crm-msg-header { flex-direction: column !important; align-items: flex-start !important; gap: 6px !important; }
          .crm-toggle-pill { transform: scale(0.92); transform-origin: left; }
          .crm-conv-actions { flex-direction: row !important; gap: 3px !important; }
          .crm-input-row { gap: 4px !important; }
          .crm-input-row input { min-width: 0 !important; font-size: 13px !important; }
          .crm-input-row button { width: 30px !important; height: 30px !important; flex-shrink: 0 !important; }
        }
      `}</style>
      <div className="crm-root" style={{
        display: 'grid',
        gridTemplateColumns: '1fr',
        gap: '0',
        borderRadius: '16px',
        border: '1px solid rgba(217, 28, 210, 0.1)',
        background: '#111111',
        boxShadow: '0 0 25px rgba(217, 28, 210, 0.04)',
        overflow: 'hidden',
      }}>
        <div className="crm-grid-premium" style={{
          display: 'grid',
          gridTemplateColumns: '1fr',
          gap: '0',
          width: '100%',
          minWidth: 0,
        }}>
          {/* Left: Conversations List — V145 mobile fix */}
          <div className="crm-conv-list" style={{
            padding: '12px 8px',
            borderRight: '1px solid rgba(217, 28, 210, 0.08)',
            background: 'rgba(26, 26, 26, 0.4)',
            minWidth: 0,
            overflow: 'hidden',
          }}>
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <MessageCircle size={16} style={{ color: '#D91CD2' }} />
                <span style={{ color: '#fff', fontSize: '14px', fontWeight: '600' }}>
                  Conversations
                </span>
                <span style={{
                  color: 'rgba(255,255,255,0.3)',
                  fontSize: '12px',
                }}>
                  {enrichedConversations.length}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                {/* v108: Create new direct conversation */}
                <button
                  onClick={() => setShowNewConversationDialog(true)}
                  style={{
                    ...iconBtn('rgba(255,255,255,0.3)'),
                    width: '28px', height: '28px',
                  }}
                  title="Nouvelle conversation"
                  onMouseEnter={(e) => { e.currentTarget.style.color = '#D91CD2'; e.currentTarget.style.boxShadow = GLOW.violetSoft; }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = 'rgba(255,255,255,0.3)'; e.currentTarget.style.boxShadow = 'none'; }}
                >
                  <MessageCircle size={14} />
                </button>
                {/* v38: Toggle bulk mode */}
                <button
                  onClick={() => bulkMode ? exitBulkMode() : setBulkMode(true)}
                  style={{
                    ...iconBtn(bulkMode ? '#ef4444' : 'rgba(255,255,255,0.3)'),
                    width: '28px', height: '28px',
                    background: bulkMode ? 'rgba(239,68,68,0.1)' : 'transparent',
                    borderRadius: '8px',
                  }}
                  title={bulkMode ? 'Annuler la sélection' : 'Sélection multiple'}
                  onMouseEnter={(e) => { e.currentTarget.style.color = bulkMode ? '#ef4444' : '#D91CD2'; e.currentTarget.style.boxShadow = bulkMode ? GLOW.red : GLOW.violetSoft; }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = bulkMode ? '#ef4444' : 'rgba(255,255,255,0.3)'; e.currentTarget.style.boxShadow = 'none'; }}
                >
                  {bulkMode ? <X size={14} /> : <Trash2 size={14} />}
                </button>
                <button
                  onClick={() => loadConversations(true)}
                  disabled={conversationsLoading}
                  style={{
                    ...iconBtn('rgba(255,255,255,0.3)'),
                    width: '28px', height: '28px',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.color = '#D91CD2'; e.currentTarget.style.boxShadow = GLOW.violetSoft; }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = 'rgba(255,255,255,0.3)'; e.currentTarget.style.boxShadow = 'none'; }}
                >
                  {conversationsLoading ? <span style={{ fontSize: '12px' }}>⏳</span> : <RefreshCw size={14} />}
                </button>
              </div>
            </div>

            {/* v38: Bulk selection bar */}
            {bulkMode && (
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '10px 14px', marginBottom: '12px', borderRadius: '12px',
                background: 'linear-gradient(135deg, rgba(239,68,68,0.08), rgba(217,28,210,0.06))',
                border: '1px solid rgba(239,68,68,0.15)',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  {/* Master checkbox */}
                  <div
                    onClick={selectAllConversations}
                    style={{
                      width: '22px', height: '22px', minWidth: '22px', borderRadius: '6px',
                      border: bulkSelected.size === enrichedConversations.length && enrichedConversations.length > 0
                        ? '2px solid #D91CD2' : '2px solid rgba(255,255,255,0.25)',
                      background: bulkSelected.size === enrichedConversations.length && enrichedConversations.length > 0
                        ? '#D91CD2' : bulkSelected.size > 0 ? 'rgba(217,28,210,0.3)' : 'transparent',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      cursor: 'pointer', transition: 'all 0.2s ease',
                    }}
                  >
                    {bulkSelected.size > 0 && <Check size={14} style={{ color: '#fff', strokeWidth: 3 }} />}
                  </div>
                  <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: '12px', fontWeight: 500 }}>
                    {bulkSelected.size === 0 ? 'Tout sélectionner' : `${bulkSelected.size} sélectionnée${bulkSelected.size > 1 ? 's' : ''}`}
                  </span>
                </div>
                {bulkSelected.size > 0 && (
                  <button
                    onClick={handleBulkDelete}
                    disabled={bulkDeleting}
                    style={{
                      display: 'flex', alignItems: 'center', gap: '6px',
                      padding: '8px 16px', borderRadius: '10px', border: 'none',
                      background: 'linear-gradient(135deg, #ef4444, #b91c1c)',
                      color: '#fff', fontSize: '12px', fontWeight: 700,
                      cursor: bulkDeleting ? 'wait' : 'pointer',
                      opacity: bulkDeleting ? 0.7 : 1,
                      boxShadow: '0 0 12px rgba(239,68,68,0.3)',
                      transition: 'all 0.2s ease',
                    }}
                    onMouseEnter={(e) => { if (!bulkDeleting) e.currentTarget.style.boxShadow = '0 0 20px rgba(239,68,68,0.5)'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.boxShadow = '0 0 12px rgba(239,68,68,0.3)'; }}
                  >
                    <Trash2 size={13} />
                    {bulkDeleting ? 'Suppression...' : `Supprimer (${bulkSelected.size})`}
                  </button>
                )}
              </div>
            )}

            {/* Search — v105 redesign */}
            <div style={{ position: 'relative', marginBottom: '16px' }}>
              <Search size={14} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'rgba(255,255,255,0.3)' }} />
              <input
                type="text"
                value={conversationSearch}
                onChange={(e) => setConversationSearch(e.target.value)}
                placeholder="Rechercher…"
                style={{
                  width: '100%',
                  padding: '10px 12px 10px 32px',
                  background: '#1A1A1A',
                  border: '1px solid rgba(217, 28, 210, 0.1)',
                  borderRadius: '10px',
                  color: '#fff',
                  fontSize: '13px',
                  outline: 'none',
                  transition: 'all 0.25s',
                }}
                onFocus={(e) => { e.target.style.borderColor = 'rgba(217, 28, 210, 0.35)'; e.target.style.boxShadow = '0 0 12px rgba(217, 28, 210, 0.08)'; }}
                onBlur={(e) => { e.target.style.borderColor = 'rgba(217, 28, 210, 0.1)'; e.target.style.boxShadow = 'none'; }}
                data-testid="conversation-search"
              />
            </div>

            {/* Liste groupée */}
            <GroupedConversationList
              enrichedConversations={enrichedConversations}
              conversationsListRef={conversationsListRef}
              handleConversationsScroll={handleConversationsScroll}
              selectedSession={selectedSession}
              setSelectedSession={setSelectedSession}
              loadSessionMessages={loadSessionMessages}
              setSessionMode={setSessionMode}
              deleteChatSession={deleteChatSession}
              isSuperAdmin={isSuperAdmin}
              conversationsHasMore={conversationsHasMore}
              conversationsLoading={conversationsLoading}
              bulkMode={bulkMode}
              bulkSelected={bulkSelected}
              toggleBulkSelect={toggleBulkSelect}
            />
          </div>

          {/* Right: Selected Conversation Messages — V145 mobile fix */}
          <div className="crm-msg-detail" style={{
            padding: '12px 8px',
            display: 'flex',
            flexDirection: 'column',
            minHeight: '350px',
            borderTop: '1px solid rgba(217, 28, 210, 0.08)',
            background: 'rgba(26, 26, 26, 0.3)',
            minWidth: 0,
            overflow: 'hidden',
          }}>
            <style>{`
              @media (min-width: 1024px) {
                .crm-msg-panel { border-top: none !important; }
              }
            `}</style>
            {selectedSession ? (
              <>
                {/* V143b: Header conversation — wraps on mobile */}
                <div className="crm-msg-panel crm-msg-header" style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  paddingBottom: '12px',
                  borderBottom: '1px solid rgba(217, 28, 210, 0.1)',
                  marginBottom: '12px',
                  flexWrap: 'wrap',
                  gap: '8px',
                }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      {(() => {
                        const isAI = selectedSession.mode === 'bot' || selectedSession.mode === 'ai' || selectedSession.is_ai_active;
                        return <div style={{
                          width: '8px', height: '8px', borderRadius: '50%',
                          background: isAI ? '#8b5cf6' : '#f59e0b',
                          boxShadow: isAI ? '0 0 6px rgba(139,92,246,0.5)' : '0 0 6px rgba(245,158,11,0.5)',
                        }} />;
                      })()}
                      <p style={{ color: '#fff', fontSize: '14px', fontWeight: '500', margin: 0 }}>
                        {selectedSession.participantName || selectedSession.participantEmail || 'Client'}
                      </p>
                    </div>
                    {selectedSession.participantEmail && (
                      <p style={{ color: 'rgba(255,255,255,0.2)', fontSize: '11px', margin: '3px 0 0 16px' }}>{selectedSession.participantEmail}</p>
                    )}
                    {selectedSession.participantWhatsapp && (
                      <p style={{ color: 'rgba(34,197,94,0.5)', fontSize: '11px', margin: '2px 0 0 16px', display: 'flex', alignItems: 'center', gap: '3px' }}>
                        <Phone size={10} /> {selectedSession.participantWhatsapp}
                      </p>
                    )}
                    {selectedSession.title && (
                      <p style={{ color: 'rgba(217, 28, 210, 0.5)', fontSize: '10px', margin: '2px 0 0 16px' }}>
                        ✦ {selectedSession.title}
                      </p>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {/* V143b: AI/Human mode toggle — compact pill for mobile */}
                    <div className="crm-toggle-pill" style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0',
                      borderRadius: '20px',
                      background: 'rgba(255,255,255,0.04)',
                      border: '1px solid rgba(255,255,255,0.08)',
                      overflow: 'hidden',
                      flexShrink: 0,
                    }}>
                      {(() => {
                        const isAI = selectedSession.mode === 'bot' || selectedSession.mode === 'ai' || selectedSession.is_ai_active;
                        return <>
                          {/* IA button */}
                          <button
                            onClick={() => { if (!isAI) handleToggleSelectedSessionAI(); }}
                            style={{
                              display: 'flex', alignItems: 'center', gap: '4px',
                              padding: '6px 12px',
                              border: 'none', cursor: 'pointer',
                              fontSize: '11px', fontWeight: '600',
                              background: isAI ? '#8b5cf6' : 'transparent',
                              color: isAI ? '#fff' : 'rgba(255,255,255,0.3)',
                              transition: 'all 0.25s ease',
                              borderRadius: '20px 0 0 20px',
                            }}
                          >
                            <Bot size={13} /> IA
                          </button>
                          {/* Manuel button */}
                          <button
                            onClick={() => { if (isAI) handleToggleSelectedSessionAI(); }}
                            style={{
                              display: 'flex', alignItems: 'center', gap: '4px',
                              padding: '6px 12px',
                              border: 'none', cursor: 'pointer',
                              fontSize: '11px', fontWeight: '600',
                              background: !isAI ? '#f59e0b' : 'transparent',
                              color: !isAI ? '#000' : 'rgba(255,255,255,0.3)',
                              transition: 'all 0.25s ease',
                              borderRadius: '0 20px 20px 0',
                            }}
                          >
                            <UserRound size={13} /> Manuel
                          </button>
                        </>;
                      })()}
                    </div>
                  </div>
                </div>

                {/* v100: Réponses tunnel (si disponibles) */}
                {selectedSession.tunnel_answers && Object.keys(selectedSession.tunnel_answers).length > 0 && (
                  <div style={{
                    marginBottom: '12px',
                    padding: '12px',
                    borderRadius: '10px',
                    background: 'rgba(217,28,210,0.06)',
                    border: '1px solid rgba(217,28,210,0.15)',
                  }}>
                    <p style={{ color: '#D91CD2', fontSize: '11px', fontWeight: 600, margin: '0 0 8px 0' }}>📋 Réponses du tunnel</p>
                    {Object.values(selectedSession.tunnel_answers).map((qa, i) => (
                      <div key={i} style={{ marginBottom: i < Object.keys(selectedSession.tunnel_answers).length - 1 ? '8px' : 0 }}>
                        <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '10px', margin: '0 0 2px 0' }}>{qa.question || `Question ${i+1}`}</p>
                        <p style={{ color: '#fff', fontSize: '12px', margin: 0, fontWeight: 500 }}>{qa.answer || '—'}</p>
                      </div>
                    ))}
                  </div>
                )}

                {/* V144: Messages — with deletion, filtered system messages, mobile overflow fix */}
                <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '8px 0', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {sessionMessages.length === 0 ? (
                    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <p style={{ color: 'rgba(255,255,255,0.15)', fontSize: '13px' }}>Aucun message</p>
                    </div>
                  ) : (
                    sessionMessages.map((msg, idx) => {
                      // V143: Filter out noisy mode-switching system messages
                      const isSystemMessage = msg.sender_type === 'system';
                      if (isSystemMessage) {
                        const sysText = (msg.content || msg.text || '').toLowerCase();
                        // Hide mode switching messages to reduce clutter
                        if (sysText.includes('humain a pris') || sysText.includes('ia est de retour') ||
                            sysText.includes('mode humain') || sysText.includes('mode ia') ||
                            sysText.includes('conseiller humain') || sysText.includes('assistant ia')) {
                          return null;
                        }
                        return (
                          <div key={msg.id || idx} style={{ display: 'flex', justifyContent: 'center' }}>
                            <span style={{
                              fontSize: '11px',
                              color: 'rgba(255,255,255,0.3)',
                              padding: '4px 14px',
                              borderRadius: '20px',
                              background: 'rgba(139, 92, 246, 0.08)',
                            }}>
                              {msg.content || msg.text || ''}
                            </span>
                          </div>
                        );
                      }

                      const isClientMessage = msg.sender_type === 'user' || msg.role === 'user';
                      const isDeleted = msg.is_deleted;
                      const msgText = msg.content || msg.text || msg.message || '[Message vide]';
                      const isAI = msg.sender_type === 'assistant' || msg.role === 'assistant';

                      return (
                        <div
                          key={msg.id || idx}
                          style={{
                            display: 'flex',
                            justifyContent: isClientMessage ? 'flex-start' : 'flex-end',
                            position: 'relative',
                            overflow: 'hidden',
                          }}
                          className="crm-msg-row"
                        >
                          <div style={{
                            maxWidth: 'min(80%, calc(100vw - 60px))',
                            padding: '8px 12px',
                            borderRadius: isClientMessage ? '4px 16px 16px 16px' : '16px 4px 16px 16px',
                            background: isClientMessage
                              ? 'rgba(255,255,255,0.06)'
                              : isAI ? 'linear-gradient(135deg, #8b5cf6, #D91CD2)' : '#D91CD2',
                            color: '#fff',
                            position: 'relative',
                          }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                              <p style={{ fontSize: '10px', fontWeight: '600', opacity: 0.5, margin: '0 0 4px', letterSpacing: '0.02em', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                {isClientMessage
                                  ? (msg.sender_name || selectedSession.participantName || 'Client')
                                  : isAI ? <><Bot size={9} /> IA</> : 'Vous'
                                }
                              </p>
                              {/* V143: Delete button */}
                              {!isDeleted && msg.id && (
                                <button
                                  onClick={() => handleDeleteMessage(msg.id)}
                                  style={{
                                    background: 'none', border: 'none', cursor: 'pointer',
                                    padding: '2px', opacity: 0.3, transition: 'opacity 0.2s',
                                    display: 'flex', alignItems: 'center',
                                  }}
                                  onMouseEnter={(e) => e.currentTarget.style.opacity = '0.8'}
                                  onMouseLeave={(e) => e.currentTarget.style.opacity = '0.3'}
                                  title="Supprimer ce message"
                                >
                                  <Trash2 size={11} color="#fff" />
                                </button>
                              )}
                            </div>
                            <p style={{ fontSize: '13px', margin: 0, lineHeight: '1.5', wordBreak: 'break-word', fontStyle: isDeleted ? 'italic' : 'normal', opacity: isDeleted ? 0.5 : 1 }}>
                              {isDeleted ? 'Message supprimé' : renderTextWithLinks(msgText)}
                            </p>
                            <p style={{ fontSize: '10px', color: 'rgba(255,255,255,0.35)', margin: '6px 0 0', textAlign: 'right' }}>
                              {(() => {
                                const dateVal = msg.timestamp || msg.createdAt || msg.created_at;
                                if (!dateVal) return '—';
                                try {
                                  const d = new Date(dateVal);
                                  return isNaN(d.getTime()) ? '—' : d.toLocaleString('fr-CH', {
                                    hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit'
                                  });
                                } catch { return '—'; }
                              })()}
                            </p>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>

                {/* V145: Input — mobile-friendly, no overflow */}
                <div className="crm-input-row" style={{
                  paddingTop: '8px',
                  borderTop: '1px solid rgba(255,255,255,0.06)',
                  display: 'flex',
                  gap: '4px',
                  alignItems: 'center',
                  position: 'relative',
                  flexWrap: 'nowrap',
                  width: '100%',
                  minWidth: 0,
                }}>
                  {/* V143: Emoji picker for coach */}
                  <AfricanEmojiPicker
                    isOpen={showCoachEmojiPicker}
                    onSelect={(emoji) => {
                      setCoachMessage(prev => prev + emoji);
                      setShowCoachEmojiPicker(false);
                    }}
                    onClose={() => setShowCoachEmojiPicker(false)}
                    position="above-input"
                  />
                  <button
                    type="button"
                    onClick={() => setShowCoachEmojiPicker(!showCoachEmojiPicker)}
                    style={{
                      width: '30px', height: '30px',
                      borderRadius: '50%',
                      background: showCoachEmojiPicker ? '#D91CD2' : 'transparent',
                      border: 'none',
                      cursor: 'pointer',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      flexShrink: 0,
                      fontSize: '16px',
                      transition: 'all 0.2s',
                    }}
                    title="Émojis Africains & Swahili"
                  >
                    😜
                  </button>
                  <input
                    type="text"
                    value={coachMessage}
                    onChange={(e) => setCoachMessage(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
                    placeholder="Votre message…"
                    style={{
                      flex: 1,
                      minWidth: 0,
                      padding: '8px 4px',
                      background: 'transparent',
                      border: 'none',
                      color: '#fff',
                      fontSize: '13px',
                      outline: 'none',
                    }}
                    data-testid="coach-message-input"
                  />
                  {/* v106.1: Bouton Réécrire IA — V143b: compact for mobile */}
                  <button
                    onClick={handleRewriteAI}
                    disabled={!coachMessage.trim() || rewritingAI}
                    title="✨ Réécrire avec l'IA Afroboost"
                    style={{
                      width: '34px', height: '34px',
                      borderRadius: '10px',
                      border: coachMessage.trim() && !rewritingAI
                        ? '1px solid rgba(217, 28, 210, 0.5)'
                        : '1px solid rgba(255,255,255,0.08)',
                      background: coachMessage.trim() && !rewritingAI
                        ? 'linear-gradient(135deg, #D91CD2, #8b5cf6)'
                        : 'rgba(255,255,255,0.04)',
                      color: coachMessage.trim() && !rewritingAI ? '#fff' : 'rgba(255,255,255,0.2)',
                      cursor: coachMessage.trim() && !rewritingAI ? 'pointer' : 'not-allowed',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                      boxShadow: coachMessage.trim() && !rewritingAI
                        ? '0 0 16px rgba(217, 28, 210, 0.45), 0 0 32px rgba(217, 28, 210, 0.15)'
                        : 'none',
                      flexShrink: 0,
                    }}
                    onMouseEnter={(e) => { if (coachMessage.trim() && !rewritingAI) { e.currentTarget.style.boxShadow = '0 0 24px rgba(217, 28, 210, 0.6), 0 0 48px rgba(217, 28, 210, 0.25)'; e.currentTarget.style.transform = 'scale(1.08)'; }}}
                    onMouseLeave={(e) => { e.currentTarget.style.boxShadow = coachMessage.trim() ? '0 0 16px rgba(217, 28, 210, 0.45), 0 0 32px rgba(217, 28, 210, 0.15)' : 'none'; e.currentTarget.style.transform = 'scale(1)'; }}
                  >
                    {rewritingAI ? <span style={{ fontSize: '14px' }}>⏳</span> : <span style={{ fontSize: '14px' }}>✨</span>}
                  </button>
                  <button
                    onClick={handleSendMessage}
                    disabled={!coachMessage.trim()}
                    style={{
                      ...iconBtn('#D91CD2'),
                      width: '34px',
                      height: '34px',
                      opacity: !coachMessage.trim() ? 0.25 : 1,
                      transition: 'all 0.25s',
                    }}
                    onMouseEnter={(e) => { if (coachMessage.trim()) e.currentTarget.style.boxShadow = GLOW.violet; }}
                    onMouseLeave={(e) => e.currentTarget.style.boxShadow = 'none'}
                    data-testid="send-message-btn"
                  >
                    <Send size={16} />
                  </button>
                </div>
              </>
            ) : (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ textAlign: 'center' }}>
                  <MessageCircle size={36} style={{ color: 'rgba(217, 28, 210, 0.15)', margin: '0 auto 12px' }} />
                  <p style={{ color: 'rgba(255,255,255,0.2)', fontSize: '13px', margin: 0 }}>Sélectionnez une conversation</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default CRMSection;

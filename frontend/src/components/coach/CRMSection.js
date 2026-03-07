// CRMSection.js - Section CRM/Conversations v16.2 PREMIUM
// Refonte visuelle minimaliste "borderless" — Fond noir profond, accents violet glow
// ANTI-BREAK: Toute la logique data/API est 100% identique à v16.1

import React, { useRef, useCallback, memo, useMemo, useState } from 'react';
import { ChevronDown, Trash2, Send, Copy, Check, ExternalLink, Phone, Edit2, Save, X, MessageCircle, Link2, Users, Bell, Zap, Search, RefreshCw, Bot, User } from 'lucide-react';

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

// ====== COMPOSANT COMMUNITY CHAT CARD — PREMIUM BORDERLESS ======
const CommunityCard = memo(({
  newCommunityName,
  setNewCommunityName,
  createCommunityChat,
  loadingConversations
}) => (
  <div style={{ padding: '20px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
      <div style={{
        width: '32px', height: '32px', borderRadius: '50%',
        background: 'rgba(34, 197, 94, 0.1)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Users size={16} style={{ color: '#22c55e' }} />
      </div>
      <span style={{ color: '#fff', fontSize: '15px', fontWeight: '600', letterSpacing: '-0.01em' }}>
        Communauté
      </span>
    </div>
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'flex-end' }}>
      <div style={{ flex: '1 1 200px' }}>
        <input
          type="text"
          value={newCommunityName}
          onChange={(e) => setNewCommunityName(e.target.value)}
          placeholder="Nom de la communauté"
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
          onFocus={(e) => e.target.style.borderBottomColor = '#22c55e'}
          onBlur={(e) => e.target.style.borderBottomColor = 'rgba(255,255,255,0.08)'}
          data-testid="community-name-input"
        />
      </div>
      <button
        onClick={createCommunityChat}
        disabled={loadingConversations || !newCommunityName.trim()}
        style={{
          padding: '10px 24px',
          background: '#22c55e',
          border: 'none',
          borderRadius: '24px',
          color: '#fff',
          fontSize: '13px',
          fontWeight: '600',
          cursor: (loadingConversations || !newCommunityName.trim()) ? 'not-allowed' : 'pointer',
          opacity: (loadingConversations || !newCommunityName.trim()) ? 0.4 : 1,
          transition: 'all 0.25s',
          boxShadow: 'none',
          whiteSpace: 'nowrap',
        }}
        onMouseEnter={(e) => { if (!loadingConversations && newCommunityName.trim()) e.target.style.boxShadow = GLOW.green; }}
        onMouseLeave={(e) => e.target.style.boxShadow = 'none'}
        data-testid="create-community-btn"
      >
        {loadingConversations ? '⏳' : '+ Créer'}
      </button>
    </div>
  </div>
));
CommunityCard.displayName = 'CommunityCard';

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
  isSuperAdmin
}) => {
  const isSelected = selectedSession?.id === session.id;
  const hasUnread = session.unreadCount > 0;

  return (
    <div
      onClick={() => {
        setSelectedSession(session);
        loadSessionMessages(session.id);
      }}
      style={{
        padding: '12px 14px',
        borderRadius: '12px',
        cursor: 'pointer',
        transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
        background: isSelected ? 'rgba(217, 28, 210, 0.1)' : 'transparent',
        borderLeft: isSelected ? '2px solid #D91CD2' : '2px solid transparent',
      }}
      onMouseEnter={(e) => { if (!isSelected) e.currentTarget.style.background = 'rgba(255,255,255,0.03)'; }}
      onMouseLeave={(e) => { if (!isSelected) e.currentTarget.style.background = 'transparent'; }}
      data-testid={`conversation-${session.id}`}
    >
      <div style={{ display: 'flex', alignItems: 'start', justifyContent: 'space-between', gap: '10px' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {/* Mode indicator — petit dot */}
            <div style={{
              width: '8px', height: '8px', borderRadius: '50%',
              background: session.mode === 'bot' ? '#8b5cf6' : '#22c55e',
              flexShrink: 0,
              boxShadow: session.mode === 'bot' ? '0 0 6px rgba(139,92,246,0.5)' : '0 0 6px rgba(34,197,94,0.5)',
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

          <p style={{ color: 'rgba(255,255,255,0.35)', fontSize: '12px', margin: '4px 0 0 16px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {session.lastMessage || 'Nouvelle conversation'}
          </p>

          {/* WhatsApp + Email — compact */}
          <div style={{ marginLeft: '16px', marginTop: '4px', display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
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
                  fontSize: '11px',
                  cursor: 'pointer',
                  padding: 0,
                  display: 'flex', alignItems: 'center', gap: '3px',
                }}
                title="Contacter sur WhatsApp"
              >
                <Phone size={10} /> {session.participantWhatsapp}
              </button>
            )}
            {session.participantEmail && session.participantEmail !== session.participantName && (
              <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: '11px' }}>
                {session.participantEmail}
              </span>
            )}
          </div>

          <div style={{ marginLeft: '16px', marginTop: '4px', display: 'flex', gap: '10px' }}>
            <span style={{ color: 'rgba(255,255,255,0.15)', fontSize: '10px' }}>
              {(() => {
                try {
                  const dateVal = session.lastActivity || session.createdAt;
                  if (!dateVal) return '—';
                  const d = new Date(dateVal);
                  return isNaN(d.getTime()) ? '—' : d.toLocaleDateString('fr-CH');
                } catch { return '—'; }
              })()}
            </span>
            <span style={{ color: 'rgba(255,255,255,0.15)', fontSize: '10px' }}>
              {session.messageCount || 0} msg
            </span>
          </div>
        </div>

        {/* Actions — icônes compactes */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center' }} onClick={(e) => e.stopPropagation()}>
          {/* Toggle Bot/Human — simple icon toggle */}
          <button
            onClick={() => setSessionMode(session.id, session.mode === 'bot' ? 'human' : 'bot')}
            style={{
              ...iconBtn(session.mode === 'bot' ? '#8b5cf6' : '#22c55e'),
              width: '30px', height: '30px',
            }}
            title={session.mode === 'bot' ? 'Passer en manuel' : 'Passer en IA'}
            onMouseEnter={(e) => e.currentTarget.style.boxShadow = session.mode === 'bot' ? GLOW.violetSoft : GLOW.green}
            onMouseLeave={(e) => e.currentTarget.style.boxShadow = 'none'}
          >
            {session.mode === 'bot' ? <Bot size={14} /> : <User size={14} />}
          </button>
          <button
            onClick={() => deleteChatSession(session.id)}
            style={{ ...iconBtn('rgba(239,68,68,0.5)'), width: '30px', height: '30px' }}
            title="Supprimer"
            onMouseEnter={(e) => { e.currentTarget.style.boxShadow = GLOW.red; e.currentTarget.style.color = '#ef4444'; }}
            onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.color = 'rgba(239,68,68,0.5)'; }}
          >
            <Trash2 size={13} />
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
  conversationsLoading
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
      style={{ maxHeight: '500px', overflowY: 'auto', paddingRight: '4px' }}
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
                  background: 'transparent',
                  border: 'none',
                  borderBottom: isCollapsed ? 'none' : '1px solid rgba(217, 28, 210, 0.08)',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
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
                  <span style={{ color: '#D91CD2', fontSize: '12px', fontWeight: '600' }}>
                    {groupKey}
                  </span>
                  <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: '11px' }}>
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
  // Community
  newCommunityName,
  setNewCommunityName,
  createCommunityChat,
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
  API_URL
}) => {
  return (
    <div style={{ background: '#000000', borderRadius: '20px', overflow: 'hidden' }}>
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

      {/* Generate Link — borderless */}
      <GenerateLinkCard
        newLinkTitle={newLinkTitle}
        setNewLinkTitle={setNewLinkTitle}
        newLinkCustomPrompt={newLinkCustomPrompt}
        setNewLinkCustomPrompt={setNewLinkCustomPrompt}
        generateShareableLink={generateShareableLink}
        loadingConversations={loadingConversations}
        isSuperAdmin={isSuperAdmin}
        enhancePromptWithAI={enhancePromptWithAI}
      />

      {/* Create Community */}
      <CommunityCard
        newCommunityName={newCommunityName}
        setNewCommunityName={setNewCommunityName}
        createCommunityChat={createCommunityChat}
        loadingConversations={loadingConversations}
      />

      {/* Chat Links List */}
      <ChatLinksList
        chatLinks={chatLinks}
        copiedLinkId={copiedLinkId}
        copyLinkToClipboard={copyLinkToClipboard}
        deleteChatLink={deleteChatLink}
        updateChatLink={updateChatLink}
      />

      {/* Main Conversations Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr',
        gap: '0',
      }}>
        {/* Responsive: on larger screens, use 2 columns */}
        <style>{`
          @media (min-width: 1024px) {
            .crm-grid-premium { grid-template-columns: 1fr 1fr !important; }
          }
        `}</style>
        <div className="crm-grid-premium" style={{
          display: 'grid',
          gridTemplateColumns: '1fr',
          gap: '0',
        }}>
          {/* Left: Conversations List */}
          <div style={{
            padding: '20px',
            borderRight: '1px solid rgba(255,255,255,0.04)',
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

            {/* Search — borderless */}
            <div style={{ position: 'relative', marginBottom: '16px' }}>
              <Search size={14} style={{ position: 'absolute', left: '0', top: '50%', transform: 'translateY(-50%)', color: 'rgba(255,255,255,0.2)' }} />
              <input
                type="text"
                value={conversationSearch}
                onChange={(e) => setConversationSearch(e.target.value)}
                placeholder="Rechercher…"
                style={{
                  width: '100%',
                  padding: '8px 8px 8px 22px',
                  background: 'transparent',
                  border: 'none',
                  borderBottom: '1px solid rgba(255,255,255,0.06)',
                  color: '#fff',
                  fontSize: '13px',
                  outline: 'none',
                  transition: 'border-color 0.2s',
                }}
                onFocus={(e) => e.target.style.borderBottomColor = 'rgba(217, 28, 210, 0.3)'}
                onBlur={(e) => e.target.style.borderBottomColor = 'rgba(255,255,255,0.06)'}
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
            />
          </div>

          {/* Right: Selected Conversation Messages */}
          <div style={{
            padding: '20px',
            display: 'flex',
            flexDirection: 'column',
            minHeight: '500px',
            borderTop: '1px solid rgba(255,255,255,0.04)',
          }}>
            <style>{`
              @media (min-width: 1024px) {
                .crm-msg-panel { border-top: none !important; }
              }
            `}</style>
            {selectedSession ? (
              <>
                {/* Header conversation */}
                <div className="crm-msg-panel" style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  paddingBottom: '14px',
                  borderBottom: '1px solid rgba(255,255,255,0.06)',
                  marginBottom: '14px',
                }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <div style={{
                        width: '8px', height: '8px', borderRadius: '50%',
                        background: selectedSession.mode === 'bot' ? '#8b5cf6' : '#22c55e',
                        boxShadow: selectedSession.mode === 'bot' ? '0 0 6px rgba(139,92,246,0.5)' : '0 0 6px rgba(34,197,94,0.5)',
                      }} />
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
                  <span style={{
                    fontSize: '11px',
                    color: selectedSession.mode === 'bot' ? '#8b5cf6' : '#22c55e',
                    fontWeight: '500',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}>
                    {selectedSession.mode === 'bot' ? <><Bot size={12} /> IA</> : <><User size={12} /> Manuel</>}
                  </span>
                </div>

                {/* Messages */}
                <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {sessionMessages.length === 0 ? (
                    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <p style={{ color: 'rgba(255,255,255,0.15)', fontSize: '13px' }}>Aucun message</p>
                    </div>
                  ) : (
                    sessionMessages.map((msg, idx) => {
                      // Messages système
                      const isSystemMessage = msg.sender_type === 'system';
                      if (isSystemMessage) {
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
                      const isCoachOrAI = msg.sender_type === 'coach' || msg.sender_type === 'assistant' ||
                                          msg.role === 'coach' || msg.role === 'assistant';

                      return (
                        <div
                          key={msg.id || idx}
                          style={{
                            display: 'flex',
                            justifyContent: isClientMessage ? 'flex-start' : 'flex-end',
                          }}
                        >
                          <div style={{
                            maxWidth: '80%',
                            padding: '10px 14px',
                            borderRadius: isClientMessage ? '4px 16px 16px 16px' : '16px 4px 16px 16px',
                            background: isClientMessage
                              ? 'rgba(255,255,255,0.06)'
                              : '#D91CD2',
                            color: '#fff',
                          }}>
                            <p style={{ fontSize: '10px', fontWeight: '600', opacity: 0.5, margin: '0 0 4px', letterSpacing: '0.02em' }}>
                              {isClientMessage
                                ? (msg.sender_name || selectedSession.participantName || 'Client')
                                : (msg.sender_type === 'assistant' || msg.role === 'assistant' ? 'IA' : 'Vous')
                              }
                            </p>
                            <p style={{ fontSize: '13px', margin: 0, lineHeight: '1.5', wordBreak: 'break-word' }}>
                              {msg.content || msg.text || msg.message || '[Message vide]'}
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

                {/* Input — borderless */}
                <div style={{
                  paddingTop: '14px',
                  borderTop: '1px solid rgba(255,255,255,0.06)',
                  display: 'flex',
                  gap: '8px',
                  alignItems: 'center',
                }}>
                  <input
                    type="text"
                    value={coachMessage}
                    onChange={(e) => setCoachMessage(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
                    placeholder="Votre message…"
                    style={{
                      flex: 1,
                      padding: '10px 0',
                      background: 'transparent',
                      border: 'none',
                      color: '#fff',
                      fontSize: '14px',
                      outline: 'none',
                    }}
                    data-testid="coach-message-input"
                  />
                  <button
                    onClick={handleSendMessage}
                    disabled={!coachMessage.trim()}
                    style={{
                      ...iconBtn('#D91CD2'),
                      width: '38px',
                      height: '38px',
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

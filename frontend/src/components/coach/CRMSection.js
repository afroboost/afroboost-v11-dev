// CRMSection.js - Section CRM/Conversations v16.0
// Extrait de CoachDashboard.js pour modularisation
// v16.0: Conversations groupées par lien + WhatsApp + toggle IA/Humain amélioré

import React, { useRef, useCallback, memo, useMemo, useState } from 'react';
import { ChevronDown, Trash2, Send, Copy, Check, ExternalLink, Phone, Edit2, Save, X } from 'lucide-react';

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
      className="flex items-center justify-between p-4 rounded-xl animate-pulse"
      style={{ background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.3), rgba(217, 28, 210, 0.2))', border: '1px solid rgba(139, 92, 246, 0.5)' }}
      data-testid="notification-permission-banner"
    >
      <div className="flex items-center gap-3">
        <span className="text-2xl">🔔</span>
        <div>
          <p className="text-white font-medium">Activez les notifications</p>
          <p className="text-white/60 text-sm">Recevez une alerte sonore et visuelle à chaque nouveau message client.</p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={() => setShowPermissionBanner(false)}
          className="px-3 py-2 text-white/60 hover:text-white text-sm"
        >
          Plus tard
        </button>
        <button
          onClick={requestNotificationAccess}
          className="px-4 py-2 rounded-lg text-white font-medium transition-all hover:scale-105"
          style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)' }}
          data-testid="enable-notifications-btn"
        >
          ✅ Activer
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
      className="flex items-center justify-between p-3 rounded-xl"
      style={{ background: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)' }}
    >
      <div className="flex items-center gap-3">
        <span className="text-xl">⚠️</span>
        <p className="text-white/90 text-sm">Notifications bloquées - Les alertes visuelles apparaîtront ici à la place.</p>
      </div>
      <button
        onClick={() => {
          alert('Pour activer les notifications:\n\n1. Cliquez sur l\'icône 🔒 dans la barre d\'adresse\n2. Trouvez "Notifications"\n3. Changez de "Bloquer" à "Autoriser"\n4. Rafraîchissez la page');
        }}
        className="px-3 py-1 text-xs rounded bg-white/10 text-white/70 hover:text-white"
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
          className="p-4 rounded-xl shadow-2xl cursor-pointer transform transition-all hover:scale-102 animate-slideIn"
          style={{ 
            background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.95), rgba(217, 28, 210, 0.9))',
            backdropFilter: 'blur(10px)',
            border: '1px solid rgba(255,255,255,0.2)'
          }}
          data-testid={`toast-${toast.id}`}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <p className="text-white font-medium text-sm flex items-center gap-2">
                💬 {toast.senderName}
              </p>
              <p className="text-white/80 text-sm mt-1 truncate">
                {toast.content.substring(0, 60)}{toast.content.length > 60 ? '...' : ''}
              </p>
              <p className="text-white/50 text-xs mt-1">Cliquez pour répondre</p>
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); dismissToast(toast.id); }}
              className="text-white/60 hover:text-white p-1"
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
  <div 
    className="p-4 rounded-xl"
    style={{ background: 'linear-gradient(135deg, rgba(34, 197, 94, 0.2), rgba(22, 163, 74, 0.1))', border: '1px solid rgba(34, 197, 94, 0.4)' }}
  >
    <div className="flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <span className="text-2xl">🔔</span>
        <div>
          <p className="text-white font-medium text-sm">Test des notifications</p>
          <p className="text-white/60 text-xs">
            Statut: {notificationPermission === 'granted' ? '✅ Activées (son + popup)' : 
                    notificationPermission === 'denied' ? '⚠️ Bloquées (fallback visuel)' : 
                    notificationPermission === 'unsupported' ? '❌ Non supportées' : 
                    '🔔 En attente (cliquez pour activer)'}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={notifyOnAiResponse}
            onChange={toggleNotifyOnAiResponse}
            className="w-4 h-4 accent-violet-500"
          />
          <span className="text-white/70 text-xs">Notifier réponses IA</span>
        </label>
        <button
          onClick={handleTestNotification}
          className="px-4 py-2 rounded-lg text-white text-sm font-medium transition-all hover:scale-105"
          style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)' }}
          data-testid="test-notification-btn"
        >
          🔔 Tester
        </button>
      </div>
    </div>
  </div>
));
NotificationTestPanel.displayName = 'NotificationTestPanel';

// ====== COMPOSANT GENERATE LINK CARD ======
const GenerateLinkCard = memo(({ 
  newLinkTitle, 
  setNewLinkTitle, 
  newLinkCustomPrompt, 
  setNewLinkCustomPrompt,
  generateShareableLink,
  loadingConversations,
  isSuperAdmin,
  enhancePromptWithAI  // v14.3: Fonction IA pour améliorer le prompt
}) => {
  const [isEnhancing, setIsEnhancing] = React.useState(false);
  
  // v14.3: Appeler l'IA pour transformer le texte brut en prompt structuré
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
  
  return (
    <div 
      className="p-6 rounded-2xl"
      style={{ background: 'linear-gradient(135deg, rgba(217, 28, 210, 0.15), rgba(139, 92, 246, 0.1))', border: '1px solid rgba(217, 28, 210, 0.3)' }}
    >
      <h3 className="text-xl font-semibold text-white mb-4">🔗 Générer un lien de chat</h3>
      <div className="flex flex-wrap gap-4 items-end">
        <div className="flex-1 min-w-[200px]">
          <label className="block text-sm text-white/60 mb-2">Titre (ex: Offre Janvier)</label>
          <input
            type="text"
            value={newLinkTitle}
            onChange={(e) => setNewLinkTitle(e.target.value)}
            placeholder="Lien de janvier"
            className="w-full px-4 py-3 rounded-lg bg-black/30 text-white border border-white/20 focus:outline-none focus:ring-2 focus:ring-violet-500"
            data-testid="link-title-input"
          />
        </div>
        {isSuperAdmin && (
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm text-white/60 mb-2">Prompt personnalisé (Super Admin)</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={newLinkCustomPrompt}
                onChange={(e) => setNewLinkCustomPrompt(e.target.value)}
                placeholder="Ex: Focus sur les cours de fitness..."
                className="flex-1 px-4 py-3 rounded-lg bg-black/30 text-white border border-white/20 focus:outline-none focus:ring-2 focus:ring-violet-500"
                data-testid="link-prompt-input"
              />
              {/* v14.3: Bouton IA pour améliorer le prompt */}
              <button
                onClick={handleEnhancePrompt}
                disabled={isEnhancing || !newLinkCustomPrompt.trim()}
                className="px-3 py-3 rounded-lg text-white transition-all hover:scale-105 disabled:opacity-50"
                style={{ background: 'linear-gradient(135deg, #f59e0b, #d97706)' }}
                title="Améliorer avec l'IA"
                data-testid="enhance-prompt-btn"
              >
                {isEnhancing ? '⏳' : '✨'}
              </button>
            </div>
          </div>
        )}
        <button
          onClick={generateShareableLink}
          disabled={loadingConversations}
          className="px-6 py-3 rounded-lg text-white font-semibold transition-all hover:scale-105 disabled:opacity-50"
          style={{ background: 'linear-gradient(135deg, #8b5cf6, #d91cd2)' }}
          data-testid="generate-link-btn"
        >
          {loadingConversations ? '⏳' : '➕ Créer le lien'}
        </button>
      </div>
    </div>
  );
});
GenerateLinkCard.displayName = 'GenerateLinkCard';

// ====== COMPOSANT COMMUNITY CHAT CARD ======
const CommunityCard = memo(({ 
  newCommunityName, 
  setNewCommunityName, 
  createCommunityChat, 
  loadingConversations 
}) => (
  <div 
    className="p-6 rounded-2xl"
    style={{ background: 'linear-gradient(135deg, rgba(34, 197, 94, 0.15), rgba(22, 163, 74, 0.1))', border: '1px solid rgba(34, 197, 94, 0.3)' }}
  >
    <h3 className="text-xl font-semibold text-white mb-4">👥 Créer une communauté</h3>
    <div className="flex flex-wrap gap-4 items-end">
      <div className="flex-1 min-w-[200px]">
        <label className="block text-sm text-white/60 mb-2">Nom de la communauté</label>
        <input
          type="text"
          value={newCommunityName}
          onChange={(e) => setNewCommunityName(e.target.value)}
          placeholder="Ex: Groupe Fitness Mars"
          className="w-full px-4 py-3 rounded-lg bg-black/30 text-white border border-white/20 focus:outline-none focus:ring-2 focus:ring-green-500"
          data-testid="community-name-input"
        />
      </div>
      <button
        onClick={createCommunityChat}
        disabled={loadingConversations || !newCommunityName.trim()}
        className="px-6 py-3 rounded-lg text-white font-semibold transition-all hover:scale-105 disabled:opacity-50"
        style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)' }}
        data-testid="create-community-btn"
      >
        {loadingConversations ? '⏳' : '👥 Créer'}
      </button>
    </div>
  </div>
));
CommunityCard.displayName = 'CommunityCard';

// ====== COMPOSANT LINK ITEM (v16.1: édition prompt après création) ======
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

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateChatLink(link.id, { title: editTitle, custom_prompt: editPrompt || null });
      setIsEditing(false);
    } catch (e) { console.error(e); }
    setSaving(false);
  };

  if (isEditing) {
    return (
      <div className="p-4 rounded-xl border border-violet-500/50" style={{ background: 'rgba(139, 92, 246, 0.1)' }}>
        <div className="space-y-3">
          <div>
            <label className="text-white/60 text-xs block mb-1">Titre du lien</label>
            <input
              value={editTitle}
              onChange={e => setEditTitle(e.target.value)}
              className="w-full p-2 rounded-lg bg-black/40 border border-white/20 text-white text-sm focus:border-violet-500 outline-none"
              placeholder="Ex: Regime Camerounais"
            />
          </div>
          <div>
            <label className="text-white/60 text-xs block mb-1">Prompt IA personnalisé</label>
            <textarea
              value={editPrompt}
              onChange={e => setEditPrompt(e.target.value)}
              rows={4}
              className="w-full p-2 rounded-lg bg-black/40 border border-white/20 text-white text-sm focus:border-violet-500 outline-none resize-none"
              placeholder="Ex: Tu es un expert diététicien spécialisé en alimentation africaine..."
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setIsEditing(false)}
              className="px-3 py-1.5 rounded-lg bg-white/10 text-white/70 text-sm hover:bg-white/20 flex items-center gap-1"
            >
              <X size={14} /> Annuler
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-3 py-1.5 rounded-lg bg-violet-600 text-white text-sm hover:bg-violet-700 flex items-center gap-1 disabled:opacity-50"
            >
              <Save size={14} /> {saving ? '...' : 'Sauvegarder'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="p-4 rounded-xl bg-black/30 border border-white/10"
      data-testid={`link-item-${link.id}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-white font-medium truncate">
            {link.title || 'Lien sans titre'}
          </p>
          <p className="text-white/40 text-xs mt-1 truncate">{fullUrl}</p>
          <div className="flex items-center gap-3 mt-2 text-xs text-white/60">
            <span>📊 {usageCount} utilisations</span>
            <span>📅 {(() => {
              try {
                const d = new Date(createdAt);
                return isNaN(d.getTime()) ? '—' : new Intl.DateTimeFormat('fr-CH', { dateStyle: 'short' }).format(d);
              } catch { return '—'; }
            })()}</span>
          </div>
        </div>
        <div className="flex items-center gap-2 ml-4">
          <button
            onClick={() => { setEditTitle(link.title || ''); setEditPrompt(customPrompt); setIsEditing(true); }}
            className="p-2 rounded-lg bg-amber-500/20 text-amber-400 hover:bg-amber-500/40 transition-colors"
            title="Modifier le prompt"
          >
            <Edit2 size={18} />
          </button>
          <button
            onClick={() => copyLinkToClipboard(linkToken)}
            className="p-2 rounded-lg bg-violet-500/20 text-violet-400 hover:bg-violet-500/40 transition-colors"
            title="Copier le lien"
            data-testid={`copy-link-${link.id}`}
          >
            {copiedLinkId === link.id ? <Check size={18} /> : <Copy size={18} />}
          </button>
          <a
            href={fullUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="p-2 rounded-lg bg-green-500/20 text-green-400 hover:bg-green-500/40 transition-colors"
            title="Ouvrir le lien"
          >
            <ExternalLink size={18} />
          </a>
          <button
            onClick={() => deleteChatLink(link.id)}
            className="p-2 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/40 transition-colors"
            title="Supprimer le lien"
            data-testid={`delete-link-${link.id}`}
          >
            <Trash2 size={18} />
          </button>
        </div>
      </div>
      {customPrompt && (
        <div className="mt-2 p-2 rounded-lg bg-violet-500/10 border border-violet-500/20">
          <p className="text-violet-300 text-xs truncate">🤖 {customPrompt}</p>
        </div>
      )}
    </div>
  );
});
LinkItem.displayName = 'LinkItem';

// ====== COMPOSANT CHAT LINKS LIST ======
const ChatLinksList = memo(({ chatLinks, copiedLinkId, copyLinkToClipboard, deleteChatLink, updateChatLink }) => {
  if (chatLinks.length === 0) return null;

  return (
    <div
      className="p-6 rounded-2xl"
      style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)' }}
    >
      <h3 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
        🔗 Liens actifs ({chatLinks.length})
      </h3>
      <div className="space-y-3 max-h-[400px] overflow-y-auto">
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

// ====== COMPOSANT CONVERSATION ITEM ======
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
      className={`p-4 rounded-xl cursor-pointer transition-all ${
        isSelected 
          ? 'bg-violet-500/30 border-violet-500' 
          : 'bg-black/30 border-white/10 hover:bg-white/5'
      } border`}
      data-testid={`conversation-${session.id}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xl">
              {session.type === 'community' ? '👥' : 
               session.mode === 'bot' ? '🤖' : '👤'}
            </span>
            <p className="text-white font-medium truncate">
              {session.participantName || session.participantEmail || 'Client'}
            </p>
            {hasUnread && (
              <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-red-500 text-white">
                {session.unreadCount}
              </span>
            )}
          </div>
          <p className="text-white/60 text-sm mt-1 truncate">
            {session.lastMessage || 'Nouvelle conversation'}
          </p>
          {/* v16.0: Afficher WhatsApp si disponible */}
          {session.participantWhatsapp && (
            <div className="flex items-center gap-2 mt-1">
              <span className="text-green-400/80 text-xs">📱 {session.participantWhatsapp}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  const phone = session.participantWhatsapp.replace(/[\s\-()]/g, '');
                  window.open(`https://wa.me/${phone.replace('+', '')}`, '_blank');
                }}
                className="text-green-400 hover:text-green-300 transition-colors"
                title="Contacter sur WhatsApp"
                style={{ padding: '2px 4px', fontSize: '10px', background: 'rgba(34, 197, 94, 0.15)', borderRadius: '4px', border: 'none', cursor: 'pointer', color: '#22c55e' }}
              >
                💬 WA
              </button>
            </div>
          )}
          {/* v14.3: Afficher email si différent du nom */}
          {session.participantEmail && session.participantEmail !== session.participantName && (
            <p className="text-white/40 text-xs mt-1">
              ✉️ {session.participantEmail}
            </p>
          )}
          <div className="flex items-center gap-3 mt-2 text-xs text-white/40">
            <span>📅 {(() => {
              try {
                const dateVal = session.lastActivity || session.createdAt;
                if (!dateVal) return '—';
                const d = new Date(dateVal);
                return isNaN(d.getTime()) ? '—' : d.toLocaleDateString('fr-CH');
              } catch { return '—'; }
            })()}</span>
            <span>💬 {session.messageCount || 0} messages</span>
          </div>
        </div>
        
        {/* Actions */}
        <div className="flex flex-col gap-1" onClick={(e) => e.stopPropagation()}>
          <select
            value={session.mode || 'bot'}
            onChange={(e) => setSessionMode(session.id, e.target.value)}
            className="px-2 py-1 text-xs rounded bg-black/40 text-white border border-white/20"
            title="Mode de conversation"
          >
            <option value="bot">🤖 Bot</option>
            <option value="human">👤 Manuel</option>
          </select>
          <button
            onClick={() => deleteChatSession(session.id)}
            className="p-1 rounded bg-red-500/20 text-red-400 hover:bg-red-500/40 text-xs"
            title="Supprimer"
          >
            🗑️
          </button>
        </div>
      </div>
    </div>
  );
});
ConversationItem.displayName = 'ConversationItem';

// ====== v16.0: COMPOSANT GROUPED CONVERSATION LIST ======
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

  // Grouper par titre de lien (ou "Sans lien" si pas de titre)
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
      style={{ maxHeight: '500px', overflowY: 'auto', paddingRight: '8px' }}
    >
      {enrichedConversations.length === 0 ? (
        <p className="text-white/40 text-center py-8">Aucune conversation pour le moment</p>
      ) : (
        groupKeys.map(groupKey => {
          const sessions = grouped[groupKey];
          const isCollapsed = collapsedGroups[groupKey];
          const totalUnread = sessions.reduce((sum, s) => sum + (s.unreadCount || 0), 0);

          return (
            <div key={groupKey} style={{ marginBottom: '16px' }}>
              {/* Header du groupe */}
              <button
                onClick={() => toggleGroup(groupKey)}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '10px 14px',
                  borderRadius: '10px',
                  border: '1px solid rgba(139, 92, 246, 0.3)',
                  background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(217, 28, 210, 0.08))',
                  cursor: 'pointer',
                  marginBottom: isCollapsed ? '0' : '8px',
                  transition: 'all 0.2s ease'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{
                    fontSize: '10px',
                    color: 'rgba(255,255,255,0.5)',
                    transform: isCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)',
                    transition: 'transform 0.2s ease',
                    display: 'inline-block'
                  }}>▼</span>
                  <span style={{ color: '#a78bfa', fontSize: '13px', fontWeight: '600' }}>
                    🔗 {groupKey}
                  </span>
                  <span style={{
                    color: 'rgba(255,255,255,0.4)',
                    fontSize: '11px'
                  }}>
                    ({sessions.length} conv.)
                  </span>
                </div>
                {totalUnread > 0 && (
                  <span style={{
                    background: '#ef4444',
                    color: '#fff',
                    fontSize: '11px',
                    fontWeight: '700',
                    padding: '2px 8px',
                    borderRadius: '10px'
                  }}>
                    {totalUnread}
                  </span>
                )}
              </button>

              {/* Conversations du groupe */}
              {!isCollapsed && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', paddingLeft: '8px' }}>
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
        <div className="text-center py-3 text-white/40">
          {conversationsLoading ? '⏳ Chargement...' : '↓ Scroll pour plus'}
        </div>
      )}
    </div>
  );
});
GroupedConversationList.displayName = 'GroupedConversationList';

// ====== COMPOSANT MAIN CRM SECTION ======
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
  enhancePromptWithAI,  // v14.3: Fonction IA pour améliorer le prompt
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
    <div className="space-y-6">
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
      
      {/* Notification Test */}
      <NotificationTestPanel 
        notificationPermission={notificationPermission}
        handleTestNotification={handleTestNotification}
        notifyOnAiResponse={notifyOnAiResponse}
        toggleNotifyOnAiResponse={toggleNotifyOnAiResponse}
      />
      
      {/* Generate Link */}
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
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Conversations List */}
        <div 
          className="p-6 rounded-2xl"
          style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)' }}
        >
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl font-semibold text-white flex items-center gap-2">
              💬 Conversations ({enrichedConversations.length})
            </h3>
            <button
              onClick={() => loadConversations(true)}
              className="px-3 py-1 text-sm rounded bg-violet-500/20 text-violet-400 hover:bg-violet-500/40"
              disabled={conversationsLoading}
            >
              {conversationsLoading ? '⏳' : '🔄'}
            </button>
          </div>
          
          {/* Search */}
          <input
            type="text"
            value={conversationSearch}
            onChange={(e) => setConversationSearch(e.target.value)}
            placeholder="🔍 Rechercher par nom, email..."
            className="w-full px-4 py-2 mb-4 rounded-lg bg-black/30 text-white border border-white/20 focus:outline-none focus:ring-2 focus:ring-violet-500"
            data-testid="conversation-search"
          />
          
          {/* v16.0: Liste groupée par lien */}
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
        <div 
          className="p-6 rounded-2xl flex flex-col"
          style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', minHeight: '600px' }}
        >
          {selectedSession ? (
            <>
              {/* Header */}
              <div className="flex items-center justify-between pb-4 border-b border-white/10">
                <div>
                  <p className="text-white font-medium flex items-center gap-2">
                    {selectedSession.type === 'community' ? '👥' : 
                     selectedSession.mode === 'bot' ? '🤖' : '👤'}
                    {selectedSession.participantName || selectedSession.participantEmail || 'Client'}
                  </p>
                  <p className="text-white/40 text-sm">{selectedSession.participantEmail || ''}</p>
                  {/* v16.0: Afficher WhatsApp si disponible */}
                  {selectedSession.participantWhatsapp && (
                    <p className="text-green-400/80 text-xs mt-1">
                      📱 {selectedSession.participantWhatsapp}
                    </p>
                  )}
                  {/* v14.3: Afficher la source du lien */}
                  {selectedSession.title && (
                    <p className="text-violet-400/80 text-xs mt-1">
                      🔗 Source : <span className="font-semibold">{selectedSession.title}</span>
                    </p>
                  )}
                </div>
                <span className={`px-2 py-1 text-xs rounded ${
                  selectedSession.mode === 'bot' ? 'bg-violet-500/20 text-violet-400' : 'bg-green-500/20 text-green-400'
                }`}>
                  {selectedSession.mode === 'bot' ? '🤖 Bot actif' : '👤 Mode manuel'}
                </span>
              </div>
              
              {/* Messages v14.3: CLIENT = Gris GAUCHE, COACH/IA = Violet DROITE */}
              <div className="flex-1 overflow-y-auto py-4 space-y-3">
                {sessionMessages.length === 0 ? (
                  <p className="text-white/40 text-center py-8">Aucun message</p>
                ) : (
                  sessionMessages.map((msg, idx) => {
                    // v16.0: Messages système (toggle IA/Humain) — centré
                    const isSystemMessage = msg.sender_type === 'system';
                    if (isSystemMessage) {
                      return (
                        <div key={msg.id || idx} style={{ display: 'flex', justifyContent: 'center' }}>
                          <div style={{
                            background: 'rgba(139, 92, 246, 0.15)',
                            border: '1px solid rgba(139, 92, 246, 0.3)',
                            borderRadius: '20px',
                            padding: '6px 16px',
                            fontSize: '12px',
                            color: 'rgba(255,255,255,0.6)'
                          }}>
                            {msg.content || msg.text || ''}
                          </div>
                        </div>
                      );
                    }

                    // v14.3: Déterminer si c'est un message du client ou du coach/IA
                    const isClientMessage = msg.sender_type === 'user' || msg.role === 'user';
                    const isCoachOrAI = msg.sender_type === 'coach' || msg.sender_type === 'assistant' ||
                                        msg.role === 'coach' || msg.role === 'assistant';

                    return (
                      <div
                        key={msg.id || idx}
                        className={`flex ${isClientMessage ? 'justify-start' : 'justify-end'}`}
                      >
                        <div
                          className={`max-w-[80%] p-3 rounded-2xl ${
                            isClientMessage
                              ? 'bg-gray-700/80 text-white' // Client: Gris foncé, GAUCHE
                              : 'text-white' // Coach/IA: Violet Afroboost, DROITE
                          }`}
                          style={!isClientMessage ? { backgroundColor: '#D91CD2' } : {}}
                        >
                          {/* v14.3: Nom de l'expéditeur */}
                          <p className="text-xs font-semibold mb-1 opacity-70">
                            {isClientMessage
                              ? (msg.sender_name || selectedSession.participantName || 'Client')
                              : (msg.sender_type === 'assistant' || msg.role === 'assistant' ? '🤖 Assistant IA' : '👤 Vous')
                            }
                          </p>
                          {/* v13.7: Fallback pour éviter les bulles vides */}
                          <p className="text-sm">{msg.content || msg.text || msg.message || '[Message vide]'}</p>
                          <p className="text-xs text-white/60 mt-1">
                            {/* v14.3: Date format fr-CH */}
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
              
              {/* Input */}
              <div className="pt-4 border-t border-white/10">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={coachMessage}
                    onChange={(e) => setCoachMessage(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
                    placeholder="Tapez votre message..."
                    className="flex-1 px-4 py-3 rounded-lg bg-black/30 text-white border border-white/20 focus:outline-none focus:ring-2 focus:ring-violet-500"
                    data-testid="coach-message-input"
                  />
                  <button
                    onClick={handleSendMessage}
                    disabled={!coachMessage.trim()}
                    className="px-4 py-3 rounded-lg text-white font-semibold transition-all hover:scale-105 disabled:opacity-50"
                    style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)' }}
                    data-testid="send-message-btn"
                  >
                    <Send size={20} />
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center text-white/40">
                <span className="text-4xl block mb-4">💬</span>
                <p>Sélectionnez une conversation</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default CRMSection;

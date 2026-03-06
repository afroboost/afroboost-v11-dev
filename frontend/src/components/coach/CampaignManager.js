/**
 * CampaignManager.js - v12: Refonte UX simplifiée
 *
 * La page ne montre que le Calendrier + Historique.
 * Le formulaire est dans un Modal étape par étape (CampaignModal).
 * Anti-break: toutes les fonctionnalités existantes sont préservées.
 */

import React, { memo, useState } from 'react';
import axios from 'axios';
import CampaignCalendar from './CampaignCalendar';
import CampaignModal from './CampaignModal';

const CampaignManager = ({
  // === ÉTATS PRINCIPAUX ===
  campaigns,
  newCampaign,
  setNewCampaign,
  editingCampaignId,
  schedulerHealth,

  // === MÉDIAS DISPONIBLES ===
  mediaLinks = [],
  // === ÉTATS ENVOI DIRECT ===
  directSendMode,
  setDirectSendMode,
  externalChannelsExpanded,
  setExternalChannelsExpanded,
  currentWhatsAppIndex,
  instagramProfile,
  setInstagramProfile,
  messageCopied,

  // === CONTACT STATS ===
  contactStats,
  allContacts,
  filteredContacts,
  selectedContactsForCampaign,
  contactSearchQuery,
  setContactSearchQuery,

  // === DESTINATAIRES (PANIER) ===
  selectedRecipients,
  setSelectedRecipients,
  activeConversations,
  setActiveConversations,
  showConversationDropdown,
  setShowConversationDropdown,
  conversationSearch,
  setConversationSearch,

  // === HISTORIQUE FILTRES ===
  campaignHistoryFilter,
  setCampaignHistoryFilter,
  campaignLogs,

  // === EMAIL RESEND ===
  emailSendingProgress,
  emailSendingResults,
  setEmailSendingResults,
  testEmailAddress,
  setTestEmailAddress,
  testEmailStatus,

  // === WHATSAPP ===
  whatsAppConfig,
  setWhatsAppConfig,
  showWhatsAppConfig,
  setShowWhatsAppConfig,
  whatsAppSendingProgress,
  whatsAppSendingResults,
  setWhatsAppSendingResults,
  testWhatsAppNumber,
  setTestWhatsAppNumber,
  testWhatsAppStatus,

  // === ENVOI GROUPÉ ===
  bulkSendingInProgress,
  bulkSendingProgress,
  bulkSendingResults,
  setBulkSendingResults,

  // === IA WHATSAPP ===
  aiConfig,
  setAiConfig,
  showAIConfig,
  setShowAIConfig,
  aiLogs,
  aiTestMessage,
  setAiTestMessage,
  aiTestResponse,
  aiTestLoading,
  aiConfigSaveStatus,

  // === PREVIEW MÉDIA ===
  resolvedThumbnail,

  // === HANDLERS ===
  handleTestEmail,
  handleSendEmailCampaign,
  handleTestWhatsApp,
  handleSendWhatsAppCampaign,
  handleBulkSendCampaign,
  handleSaveWhatsAppConfig,
  handleSaveAIConfig,
  handleTestAI,
  handleClearAILogs,
  handleEditCampaign,

  // === FONCTIONS CAMPAGNES ===
  createCampaign,
  cancelEditCampaign,
  launchCampaignWithSend,
  deleteCampaign,
  addScheduleSlot,
  removeScheduleSlot,
  updateScheduleSlot,

  // === FONCTIONS CONTACTS ===
  toggleContactForCampaign,
  toggleAllContacts,
  getContactsForDirectSend,
  getCurrentWhatsAppContact,
  nextWhatsAppContact,
  prevWhatsAppContact,

  // === FONCTIONS LIENS ===
  formatPhoneForWhatsApp,
  generateWhatsAppLink,
  generateGroupedEmailLink,
  generateEmailLink,
  copyMessageForInstagram,
  markResultSent,

  // === UTILS ===
  showCampaignToast,
  API,

  // === CRÉDITS ===
  hasInsufficientCredits = false,
  coachCredits = null,
  isSuperAdmin = false,
  campaignCreditCost = 1
}) => {
  // v12: Modal state
  const [showModal, setShowModal] = useState(false);
  const [preSelectedDate, setPreSelectedDate] = useState(null);

  // Credit block message
  const creditBlockMessage = hasInsufficientCredits ? (
    <div style={{ padding: '16px', borderRadius: '10px', marginBottom: '16px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)' }}>
      <p style={{ color: '#f87171', fontWeight: 500, margin: '0 0 4px' }}>⚠️ Crédits insuffisants</p>
      <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '13px', margin: '0 0 8px' }}>Achetez un pack de crédits pour envoyer des campagnes.</p>
      <a href="/#devenir-coach" style={{ display: 'inline-block', padding: '8px 16px', borderRadius: '8px', fontSize: '13px', fontWeight: 600, background: 'linear-gradient(135deg, #d91cd2, #8b5cf6)', color: 'white', textDecoration: 'none' }}>
        Acheter des crédits
      </a>
    </div>
  ) : null;

  // Open modal for new campaign
  const openNewCampaign = (dateStr) => {
    cancelEditCampaign?.(); // Reset form
    setPreSelectedDate(dateStr || null);
    setShowModal(true);
  };

  // Open modal for editing
  const openEditCampaign = (campaign) => {
    handleEditCampaign?.(campaign);
    setPreSelectedDate(null);
    setShowModal(true);
  };

  // Move campaign (drag & drop)
  const handleMoveCampaign = async (campaignId, newDateStr) => {
    try {
      const newScheduledAt = `${newDateStr}T10:00:00`;
      await axios.put(`${API}/campaigns/${campaignId}`, { scheduledAt: newScheduledAt });
      showCampaignToast?.(`📅 Campagne déplacée au ${newDateStr}`, 'success');
      // Refresh will happen via parent state
      window.location.reload(); // Simple refresh for now
    } catch (err) {
      showCampaignToast?.(`Erreur: ${err.message}`, 'error');
    }
  };

  // Duplicate campaign
  const handleDuplicateCampaign = async (campaign) => {
    try {
      const dupData = {
        name: `${campaign.name} (copie)`,
        message: campaign.message || '',
        mediaUrl: campaign.mediaUrl || '',
        mediaFormat: campaign.mediaFormat || '16:9',
        targetType: campaign.targetType || 'all',
        selectedContacts: campaign.selectedContacts || [],
        channels: campaign.channels || { internal: true },
        targetGroupId: campaign.targetGroupId || 'community',
        targetIds: campaign.targetIds || [],
        targetConversationId: campaign.targetConversationId || '',
        targetConversationName: campaign.targetConversationName || '',
        systemPrompt: campaign.systemPrompt || null,
        descriptionPrompt: campaign.descriptionPrompt || null,
        ctaType: campaign.ctaType || null,
        ctaText: campaign.ctaText || null,
        ctaLink: campaign.ctaLink || null,
        scheduledAt: null
      };
      await axios.post(`${API}/campaigns`, dupData);
      showCampaignToast?.(`📋 "${campaign.name}" dupliquée`, 'success');
      window.location.reload();
    } catch (err) {
      showCampaignToast?.(`Erreur duplication: ${err.message}`, 'error');
    }
  };

  // Handle modal close
  const handleModalClose = () => {
    setShowModal(false);
    setPreSelectedDate(null);
    cancelEditCampaign?.();
  };

  return (
    <div className="card-gradient rounded-xl p-4 sm:p-6">
      {creditBlockMessage}

      {/* Header simplifié */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
        <h2 style={{ color: '#fff', fontSize: '18px', fontWeight: 600, margin: 0 }}>📢 Campagnes</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {/* Scheduler health badge */}
          {(() => {
            const isActive = schedulerHealth?.status === "active" && schedulerHealth?.last_run;
            const lastRunDate = schedulerHealth?.last_run ? new Date(schedulerHealth.last_run) : null;
            const diffSeconds = lastRunDate ? Math.floor((new Date() - lastRunDate) / 1000) : 999;
            const isHealthy = isActive && diffSeconds < 60;
            return (
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: '6px',
                padding: '4px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 500,
                background: isHealthy ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                border: `1px solid ${isHealthy ? 'rgba(34,197,94,0.4)' : 'rgba(239,68,68,0.4)'}`,
                color: isHealthy ? '#4ade80' : '#f87171'
              }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: isHealthy ? '#22c55e' : '#ef4444' }} />
                {isHealthy ? 'Automate actif' : 'Automate arrêté'}
              </span>
            );
          })()}
        </div>
      </div>

      {/* === CALENDRIER (point d'entrée principal) === */}
      <CampaignCalendar
        campaigns={campaigns}
        onDayClick={openNewCampaign}
        onCampaignClick={openEditCampaign}
        onMoveCampaign={handleMoveCampaign}
        onDuplicateCampaign={handleDuplicateCampaign}
      />

      {/* === MODAL TUNNEL 3 ÉTAPES === */}
      <CampaignModal
        isOpen={showModal}
        onClose={handleModalClose}
        newCampaign={newCampaign}
        setNewCampaign={setNewCampaign}
        editingCampaignId={editingCampaignId}
        selectedRecipients={selectedRecipients}
        setSelectedRecipients={setSelectedRecipients}
        activeConversations={activeConversations}
        showConversationDropdown={showConversationDropdown}
        setShowConversationDropdown={setShowConversationDropdown}
        conversationSearch={conversationSearch}
        setConversationSearch={setConversationSearch}
        mediaLinks={mediaLinks}
        resolvedThumbnail={resolvedThumbnail}
        aiConfig={aiConfig}
        API={API}
        isSuperAdmin={isSuperAdmin}
        campaignCreditCost={campaignCreditCost}
        coachCredits={coachCredits}
        createCampaign={createCampaign}
        cancelEditCampaign={cancelEditCampaign}
        showCampaignToast={showCampaignToast}
        addScheduleSlot={addScheduleSlot}
        removeScheduleSlot={removeScheduleSlot}
        updateScheduleSlot={updateScheduleSlot}
        preSelectedDate={preSelectedDate}
      />

      {/* === HISTORIQUE DES CAMPAGNES === */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px', flexWrap: 'wrap', gap: '8px' }}>
          <h3 style={{ color: '#fff', fontWeight: 600, fontSize: '14px', margin: 0 }}>📊 Historique</h3>
          <div style={{ display: 'flex', gap: '4px' }}>
            {[
              { key: 'all', label: `Tout (${campaigns.length})` },
              { key: 'groups', label: '👥 Groupes' },
              { key: 'individuals', label: '👤 Individuels' }
            ].map(f => (
              <button key={f.key} type="button" onClick={() => setCampaignHistoryFilter(f.key)}
                style={{
                  padding: '5px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: 500, cursor: 'pointer', border: 'none',
                  background: campaignHistoryFilter === f.key ? '#7c3aed' : 'rgba(255,255,255,0.08)',
                  color: campaignHistoryFilter === f.key ? '#fff' : 'rgba(255,255,255,0.5)'
                }}>{f.label}</button>
            ))}
          </div>
        </div>

        {/* Error logs */}
        {campaignLogs.filter(l => l.type === 'error').length > 0 && (
          <div style={{ marginBottom: '12px', padding: '10px', borderRadius: '8px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
              <span style={{ width: '8px', height: '8px', background: '#ef4444', borderRadius: '50%' }} />
              <span style={{ color: '#f87171', fontWeight: 600, fontSize: '12px' }}>Erreurs récentes</span>
            </div>
            <div style={{ maxHeight: '80px', overflowY: 'auto' }}>
              {campaignLogs.filter(l => l.type === 'error').slice(0, 5).map(log => (
                <p key={log.id} style={{ fontSize: '11px', color: '#fca5a5', margin: '2px 0' }}>{log.message}</p>
              ))}
            </div>
          </div>
        )}

        {/* Campaign table */}
        <div style={{ overflowX: 'auto', overflowY: 'auto', maxHeight: '400px', borderRadius: '8px', border: '1px solid rgba(139,92,246,0.15)' }}>
          <table style={{ width: '100%', minWidth: '600px', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ textAlign: 'left', fontSize: '12px', color: 'rgba(255,255,255,0.5)', borderBottom: '1px solid rgba(139,92,246,0.2)' }}>
                <th style={{ padding: '10px 12px', background: '#0d0a14', position: 'sticky', top: 0, zIndex: 2 }}>Campagne</th>
                <th style={{ padding: '10px 8px', background: '#0d0a14', position: 'sticky', top: 0, zIndex: 2 }}>Contacts</th>
                <th style={{ padding: '10px 8px', background: '#0d0a14', position: 'sticky', top: 0, zIndex: 2 }}>Canaux</th>
                <th style={{ padding: '10px 8px', background: '#0d0a14', position: 'sticky', top: 0, zIndex: 2 }}>Statut</th>
                <th style={{ padding: '10px 8px', background: '#0d0a14', position: 'sticky', top: 0, zIndex: 2 }}>Date</th>
                <th style={{ padding: '10px 8px', background: '#0d0a14', position: 'sticky', top: 0, zIndex: 2 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {campaigns
                .filter(campaign => {
                  if (campaignHistoryFilter === 'all') return true;
                  const convType = activeConversations.find(ac => ac.conversation_id === campaign.targetConversationId)?.type;
                  if (campaignHistoryFilter === 'groups') return campaign.channels?.group || convType === 'group';
                  if (campaignHistoryFilter === 'individuals') return convType === 'user';
                  return true;
                })
                .map(campaign => {
                  const failedCount = campaign.results?.filter(r => r.status === 'failed').length || 0;
                  const hasErrors = failedCount > 0;
                  const convType = activeConversations.find(ac => ac.conversation_id === campaign.targetConversationId)?.type;

                  return (
                    <tr key={campaign.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', color: '#fff', fontSize: '13px' }}>
                      <td style={{ padding: '10px 12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          {hasErrors && <span style={{ width: '6px', height: '6px', background: '#ef4444', borderRadius: '50%', flexShrink: 0 }} />}
                          <span style={{ fontWeight: 500 }}>{campaign.name}</span>
                        </div>
                      </td>
                      <td style={{ padding: '10px 8px', fontSize: '12px' }}>
                        {campaign.channels?.internal ? (
                          <span>{convType === 'group' ? '👥' : '👤'} {(campaign.targetConversationName || 'Chat').slice(0, 20)}</span>
                        ) : campaign.targetType === 'all' ? `Tous (${campaign.results?.length || 0})` : (campaign.selectedContacts?.length || 0)}
                      </td>
                      <td style={{ padding: '10px 8px', fontSize: '12px' }}>
                        {campaign.channels?.whatsapp && '📱'}
                        {campaign.channels?.email && '📧'}
                        {campaign.channels?.group && '💬'}
                        {campaign.channels?.internal && '💌'}
                      </td>
                      <td style={{ padding: '10px 8px' }}>
                        {campaign.status === 'draft' && <span style={{ padding: '3px 8px', borderRadius: '4px', fontSize: '11px', background: 'rgba(107,114,128,0.3)', color: '#9ca3af' }}>📝 Brouillon</span>}
                        {campaign.status === 'scheduled' && <span style={{ padding: '3px 8px', borderRadius: '4px', fontSize: '11px', background: 'rgba(234,179,8,0.2)', color: '#fbbf24' }}>📅 Programmé</span>}
                        {campaign.status === 'sending' && <span style={{ padding: '3px 8px', borderRadius: '4px', fontSize: '11px', background: 'rgba(59,130,246,0.3)', color: '#60a5fa' }}>🔄 En cours</span>}
                        {(campaign.status === 'completed' || campaign.status === 'sent') && !hasErrors && <span style={{ padding: '3px 8px', borderRadius: '4px', fontSize: '11px', background: 'rgba(34,197,94,0.2)', color: '#4ade80' }}>✅ Envoyé</span>}
                        {(campaign.status === 'completed' || campaign.status === 'sent') && hasErrors && <span style={{ padding: '3px 8px', borderRadius: '4px', fontSize: '11px', background: 'rgba(249,115,22,0.2)', color: '#fb923c' }}>⚠️ Partiel</span>}
                        {campaign.status === 'failed' && <span style={{ padding: '3px 8px', borderRadius: '4px', fontSize: '11px', background: 'rgba(239,68,68,0.2)', color: '#f87171' }}>❌ Échoué</span>}
                      </td>
                      <td style={{ padding: '10px 8px', fontSize: '11px', color: 'rgba(255,255,255,0.4)' }}>
                        {campaign.scheduledAt ? new Date(campaign.scheduledAt).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : 'Immédiat'}
                      </td>
                      <td style={{ padding: '10px 8px' }}>
                        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                          <button type="button" onClick={() => openEditCampaign(campaign)}
                            style={{ padding: '4px 8px', borderRadius: '4px', fontSize: '11px', background: 'rgba(234,179,8,0.2)', border: 'none', color: '#fbbf24', cursor: 'pointer' }} title="Modifier">✏️</button>
                          {campaign.status === 'draft' && (
                            <button type="button" onClick={(e) => launchCampaignWithSend(e, campaign.id)}
                              style={{ padding: '4px 8px', borderRadius: '4px', fontSize: '11px', background: 'rgba(139,92,246,0.3)', border: 'none', color: '#c4b5fd', cursor: 'pointer' }}>🚀</button>
                          )}
                          {campaign.status === 'scheduled' && (
                            <span style={{ padding: '4px 8px', borderRadius: '4px', fontSize: '11px', background: 'rgba(234,179,8,0.1)', color: '#fbbf24' }}>⏳</span>
                          )}
                          {(campaign.status === 'sent' || campaign.status === 'completed' || campaign.status === 'failed') && (
                            <button type="button" onClick={(e) => launchCampaignWithSend(e, campaign.id)}
                              style={{ padding: '4px 8px', borderRadius: '4px', fontSize: '11px', background: 'rgba(34,197,94,0.2)', border: 'none', color: '#4ade80', cursor: 'pointer' }}>🔄</button>
                          )}
                          <button type="button" onClick={() => deleteCampaign(campaign.id)}
                            style={{ padding: '4px 8px', borderRadius: '4px', fontSize: '11px', background: 'rgba(239,68,68,0.15)', border: 'none', color: '#f87171', cursor: 'pointer' }}>🗑️</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              {campaigns.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ padding: '40px 0', textAlign: 'center', color: 'rgba(255,255,255,0.3)', fontSize: '14px' }}>
                    Cliquez sur un jour du calendrier pour créer votre première campagne
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Expanded sending details */}
        {campaigns.filter(c => c.status === 'sending').map(campaign => {
          const getWhatsAppLinkOrError = (result) => {
            if (result.channel !== 'whatsapp') return { link: null, error: false };
            const link = generateWhatsAppLink(result.contactPhone, campaign.message, campaign.mediaUrl, result.contactName);
            return { link, error: !link };
          };

          return (
            <div key={`detail-${campaign.id}`} style={{ marginTop: '16px', padding: '14px', borderRadius: '10px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(139,92,246,0.2)' }}>
              <h4 style={{ color: '#fff', fontWeight: 600, fontSize: '14px', marginTop: 0, marginBottom: '10px' }}>🔄 {campaign.name} — En cours</h4>
              <div style={{ maxHeight: '250px', overflowY: 'auto' }}>
                {campaign.results?.map((result, idx) => {
                  const waResult = result.channel === 'whatsapp' ? getWhatsAppLinkOrError(result) : { link: null, error: false };
                  const hasError = (result.channel === 'whatsapp' && waResult.error) || (result.channel === 'email' && !result.contactEmail) || result.status === 'failed';
                  return (
                    <div key={idx} style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px',
                      padding: '8px', borderRadius: '6px', marginBottom: '4px',
                      background: hasError ? 'rgba(239,68,68,0.1)' : 'rgba(0,0,0,0.2)',
                      border: hasError ? '1px solid rgba(239,68,68,0.2)' : 'none'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flex: 1, minWidth: 0 }}>
                        <span style={{ color: '#fff', fontSize: '13px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{result.contactName}</span>
                        <span style={{ fontSize: '11px', opacity: 0.4 }}>{result.channel === 'whatsapp' ? '📱' : result.channel === 'email' ? '📧' : '💌'}</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        {result.status === 'pending' && !hasError && (
                          <a href={result.channel === 'whatsapp' ? waResult.link : result.channel === 'email' ? generateEmailLink(result.contactEmail, campaign.name, campaign.message, campaign.mediaUrl, result.contactName) : '#'}
                            target="_blank" rel="noopener noreferrer"
                            onClick={() => markResultSent(campaign.id, result.contactId, result.channel)}
                            style={{ padding: '4px 10px', borderRadius: '4px', fontSize: '11px', background: '#7c3aed', color: '#fff', textDecoration: 'none' }}>Envoyer</a>
                        )}
                        {result.status === 'sent' && (
                          <>
                            <span style={{ padding: '3px 6px', borderRadius: '4px', fontSize: '10px', background: 'rgba(34,197,94,0.2)', color: '#4ade80' }}>✅</span>
                            {result.deliveredAt && <span style={{ fontSize: '10px', color: '#60a5fa' }} title={`Reçu: ${new Date(result.deliveredAt).toLocaleString('fr-FR')}`}>📬</span>}
                            {result.readAt && <span style={{ fontSize: '10px', color: '#c084fc' }} title={`Lu: ${new Date(result.readAt).toLocaleString('fr-FR')}`}>👁️</span>}
                          </>
                        )}
                        {result.status === 'failed' && <span style={{ fontSize: '10px', color: '#f87171' }} title={result.error}>❌</span>}
                        {result.status === 'pending' && hasError && <span style={{ fontSize: '10px', color: '#f87171' }}>❌ Invalide</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div style={{ marginTop: '8px', fontSize: '11px', color: '#a78bfa' }}>
                Progression: {campaign.results?.filter(r => r.status === 'sent').length || 0}/{campaign.results?.length || 0}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default memo(CampaignManager);

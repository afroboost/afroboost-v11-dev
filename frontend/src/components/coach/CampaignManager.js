/**
 * CampaignManager.js - Gestionnaire de Campagnes Marketing
 * 
 * Extrait de CoachDashboard.js pour alléger le fichier principal (~1490 lignes).
 * Composant presentationnel: reçoit tous les états et handlers via props.
 * 
 * ⚠️ SECTION CRITIQUE: Ne pas modifier la logique du badge ⏳ Auto
 * v9.4.1: Ajout de l'assistant IA pour suggestions de messages
 */

import React, { memo, useState } from 'react';
import axios from 'axios';
import { isWhatsAppConfigured } from '../../services/whatsappService';
import { parseMediaUrl } from '../../services/MediaParser';
import CampaignCalendar from './CampaignCalendar'; // v11: Calendrier interactif

const CampaignManager = ({
  // === ÉTATS PRINCIPAUX ===
  campaigns,
  newCampaign,
  setNewCampaign,
  editingCampaignId,
  schedulerHealth,
  
  // === MÉDIAS DISPONIBLES ===
  mediaLinks = [], // Liste des médias enregistrés
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
  aiConfigSaveStatus, // v9.3.8: Indicateur auto-save
  
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
  
  // === v9.0.2: CRÉDITS ===
  hasInsufficientCredits = false,
  coachCredits = null,
  // v11: Super Admin + coût campagne
  isSuperAdmin = false,
  campaignCreditCost = 1
}) => {
  // v9.0.2: Message de blocage crédits
  const creditBlockMessage = hasInsufficientCredits ? (
    <div className="p-4 rounded-lg mb-4" style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)' }}>
      <p className="text-red-400 font-medium">⚠️ Crédits insuffisants</p>
      <p className="text-white/70 text-sm mt-1">Achetez un pack de crédits pour envoyer des campagnes.</p>
      <a href="/#devenir-coach" className="inline-block mt-2 px-4 py-2 rounded-lg text-sm font-semibold" style={{ background: 'linear-gradient(135deg, #d91cd2, #8b5cf6)', color: 'white' }}>
        Acheter des crédits
      </a>
    </div>
  ) : null;
  
  // === v9.4.1: États pour l'assistant IA de campagne ===
  const [aiSuggestions, setAiSuggestions] = useState([]); // 3 suggestions de messages
  const [aiSuggestionsLoading, setAiSuggestionsLoading] = useState(false);
  const [showAiSuggestions, setShowAiSuggestions] = useState(false);
  // v11: campaignGoal remplacé par newCampaign.descriptionPrompt (persisté dans la campagne)
  const campaignGoal = newCampaign.descriptionPrompt || '';
  const setCampaignGoal = (val) => setNewCampaign(prev => ({ ...prev, descriptionPrompt: typeof val === 'function' ? val(prev.descriptionPrompt || '') : val }));

  // === v11: Fonction pour générer des suggestions avec l'IA (prompts indépendants) ===
  const generateAiSuggestions = async () => {
    const descPrompt = (newCampaign.descriptionPrompt || '').trim();
    const sysPrompt = (newCampaign.systemPrompt || '').trim();
    if (!descPrompt && !sysPrompt && !aiConfig?.campaignPrompt?.trim()) {
      showCampaignToast('⚠️ Définissez un objectif ou un prompt de campagne d\'abord', 'error');
      return;
    }

    setAiSuggestionsLoading(true);
    setShowAiSuggestions(true);

    try {
      const prompt = descPrompt || aiConfig?.campaignPrompt || '';
      const response = await axios.post(`${API}/ai/campaign-suggestions`, {
        campaign_goal: prompt,
        campaign_name: newCampaign.name || 'Campagne',
        recipient_count: selectedRecipients.length || 1,
        // v11: Envoyer les prompts indépendants de la campagne
        system_prompt: sysPrompt,
        description_prompt: descPrompt
      });
      
      if (response.data.suggestions && response.data.suggestions.length > 0) {
        setAiSuggestions(response.data.suggestions);
        showCampaignToast('✨ 3 suggestions générées!', 'success');
      } else {
        showCampaignToast('❌ Aucune suggestion générée', 'error');
      }
    } catch (err) {
      console.error('[AI SUGGESTIONS] Error:', err);
      showCampaignToast(`Erreur IA: ${err.response?.data?.detail || err.message}`, 'error');
      setAiSuggestions([
        { type: 'Promo', text: `🔥 Salut {prénom}! Offre spéciale: ${campaignGoal || 'découvre nos cours'}! Réserve maintenant.` },
        { type: 'Relance', text: `👋 Hey {prénom}! On ne t'a pas vu depuis un moment... ${campaignGoal || 'Reviens nous voir'}!` },
        { type: 'Info', text: `📢 {prénom}, ${campaignGoal || 'nouvelle info importante'}! À bientôt.` }
      ]);
    } finally {
      setAiSuggestionsLoading(false);
    }
  };
  
  // === v9.4.1: Fonction pour insérer une suggestion dans le message ===
  const insertSuggestion = (text) => {
    setNewCampaign(prev => ({ ...prev, message: text }));
    setShowAiSuggestions(false);
    showCampaignToast('✅ Message inséré!', 'success');
  };
  
  return (
    <div className="card-gradient rounded-xl p-4 sm:p-6">
      {/* v9.0.2: Blocage si crédits insuffisants */}
      {creditBlockMessage}
      
      {/* Header responsive */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-6">
        <h2 className="font-semibold text-white text-lg sm:text-xl">📢 Gestionnaire de Campagnes</h2>
        
        {/* === BADGE DE SANTÉ DU SCHEDULER === */}
        {(() => {
          const isActive = schedulerHealth.status === "active" && schedulerHealth.last_run;
          const lastRunDate = schedulerHealth.last_run ? new Date(schedulerHealth.last_run) : null;
          const now = new Date();
          const diffSeconds = lastRunDate ? Math.floor((now - lastRunDate) / 1000) : 999;
          const isRecent = diffSeconds < 60;
          const isHealthy = isActive && isRecent;
          
          return (
            <div 
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${
                isHealthy 
                  ? 'bg-green-500/20 border border-green-500/50 text-green-400' 
                  : 'bg-red-500/20 border border-red-500/50 text-red-400'
              }`}
              title={lastRunDate ? `Dernier scan: ${lastRunDate.toLocaleTimeString()}` : 'Statut inconnu'}
            >
              <span className={`w-2 h-2 rounded-full ${isHealthy ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></span>
              {isHealthy ? '● Automate : Actif' : '● Automate : Arrêté'}
            </div>
          );
        })()}
      </div>
      
      {/* === SECTION CANAUX EXTERNES (masquée par défaut - pour plus tard) === */}
      <div style={{ display: externalChannelsExpanded ? 'block' : 'none' }}>
        {/* === COMPTEUR DE CLIENTS CIBLÉS (Responsive) === */}
        <div className="mb-6 p-4 rounded-xl glass border border-purple-500/30">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div>
              <h3 className="text-white font-semibold text-base sm:text-lg">
                👥 Clients ciblés : <span className="text-pink-400">{contactStats.total}</span>
              </h3>
              <p className="text-xs sm:text-sm text-white/60 mt-1">
                📧 {contactStats.withEmail} email • 📱 {contactStats.withPhone} WhatsApp
              </p>
            </div>
            {/* Bouton envoi direct - responsive */}
            <div className="w-full sm:w-auto">
              <button 
                type="button"
                onClick={() => setDirectSendMode(!directSendMode)}
                className={`w-full sm:w-auto px-4 py-2 rounded-lg text-sm font-medium transition-all ${directSendMode ? 'bg-pink-600 text-white' : 'glass text-white border border-purple-500/30'}`}
                data-testid="direct-send-mode-btn"
              >
                {directSendMode ? '✓ Mode Envoi Direct' : '🚀 Envoi Direct'}
              </button>
            </div>
          </div>
        </div>

      {/* === MODE ENVOI DIRECT === */}
      {directSendMode && (
        <div className="mb-8 p-5 rounded-xl glass border-2 border-pink-500/50">
          <h3 className="text-white font-semibold mb-4 flex items-center gap-2">
            🚀 Envoi Direct par Canal
            <span className="text-xs text-pink-400 font-normal">(Utilisez le message ci-dessous)</span>
          </h3>

          {/* Message pour envoi direct */}
          <div className="mb-4">
            <label className="block mb-2 text-white text-sm">Message à envoyer</label>
            <textarea 
              value={newCampaign.message} 
              onChange={e => setNewCampaign({...newCampaign, message: e.target.value})}
              className="w-full px-4 py-3 rounded-lg neon-input" 
              rows={3}
              placeholder="Votre message... (utilisez {prénom} pour personnaliser)"
            />
          </div>

          {/* Champ URL média/miniature */}
          <div className="mb-4">
            <label className="block mb-2 text-white text-sm">📎 URL du média (image/vidéo)</label>
            <input 
              type="url"
              value={newCampaign.mediaUrl} 
              onChange={e => setNewCampaign({...newCampaign, mediaUrl: e.target.value})}
              className="w-full px-4 py-3 rounded-lg neon-input" 
              placeholder="https://example.com/image.jpg (optionnel)"
            />
            {newCampaign.mediaUrl && (
              <div className="mt-2 flex items-center gap-3">
                <span className="text-xs text-green-400">✓ Média attaché</span>
                <img 
                  src={newCampaign.mediaUrl} 
                  alt="Aperçu" 
                  className="w-12 h-12 rounded object-cover border border-purple-500/30"
                  onError={(e) => { e.target.style.display = 'none'; }}
                />
              </div>
            )}
          </div>

          {/* === BARRE DE PROGRESSION GROUPÉE === */}
          {bulkSendingProgress && (
            <div className="mb-4 p-4 rounded-xl bg-gradient-to-r from-blue-900/30 to-green-900/30 border border-purple-500/30">
              <div className="flex justify-between text-sm text-white mb-2">
                <span className="font-semibold">
                  {bulkSendingProgress.channel === 'email' ? '📧 Envoi Emails...' : '📱 Envoi WhatsApp...'}
                </span>
                <span>{bulkSendingProgress.current}/{bulkSendingProgress.total}</span>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-3">
                <div 
                  className={`h-3 rounded-full transition-all duration-300 ${
                    bulkSendingProgress.channel === 'email' ? 'bg-blue-500' : 'bg-green-500'
                  }`}
                  style={{ width: `${(bulkSendingProgress.current / bulkSendingProgress.total) * 100}%` }}
                />
              </div>
              {bulkSendingProgress.name && (
                <p className="text-xs text-white/70 mt-1 truncate">→ {bulkSendingProgress.name}</p>
              )}
            </div>
          )}

          {/* === RÉSULTATS ENVOI GROUPÉ === */}
          {bulkSendingResults && !bulkSendingProgress && (
            <div className="mb-4 p-4 rounded-xl bg-black/30 border border-green-500/30">
              <div className="flex justify-between items-center mb-2">
                <h4 className="text-white font-semibold">📊 Récapitulatif d'envoi</h4>
                <button 
                  type="button"
                  onClick={() => setBulkSendingResults(null)}
                  className="text-white/60 hover:text-white"
                >×</button>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                {bulkSendingResults.email && (
                  <div className="p-2 rounded bg-blue-900/30">
                    <span className="text-blue-400">📧 Emails:</span>
                    <span className="text-white ml-2">{bulkSendingResults.email.sent} ✅</span>
                    {bulkSendingResults.email.failed > 0 && (
                      <span className="text-red-400 ml-1">{bulkSendingResults.email.failed} ❌</span>
                    )}
                  </div>
                )}
                {bulkSendingResults.whatsapp && (
                  <div className="p-2 rounded bg-green-900/30">
                    <span className="text-green-400">📱 WhatsApp:</span>
                    <span className="text-white ml-2">{bulkSendingResults.whatsapp.sent} ✅</span>
                    {bulkSendingResults.whatsapp.failed > 0 && (
                      <span className="text-red-400 ml-1">{bulkSendingResults.whatsapp.failed} ❌</span>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* === BOUTON ENVOI GROUPÉ === */}
          <div className="mb-4">
            <button 
              type="button"
              onClick={(e) => !hasInsufficientCredits && handleBulkSendCampaign(e)}
              disabled={bulkSendingInProgress || hasInsufficientCredits}
              className="w-full py-4 rounded-xl font-bold text-white text-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: hasInsufficientCredits ? 'rgba(100,100,100,0.3)' : 'linear-gradient(135deg, #3b82f6 0%, #22c55e 50%, #d91cd2 100%)',
                boxShadow: (bulkSendingInProgress || hasInsufficientCredits) ? 'none' : '0 0 20px rgba(217, 28, 210, 0.4)'
              }}
              data-testid="bulk-send-campaign-btn"
              title={hasInsufficientCredits ? 'Crédits insuffisants' : ''}
            >
              {hasInsufficientCredits ? '🔒 Crédits insuffisants' : bulkSendingInProgress ? '⏳ Envoi en cours...' : '🚀 Envoyer Email + WhatsApp'}
            </button>
            <p className="text-xs text-white/50 text-center mt-2">
              {hasInsufficientCredits ? 'Rechargez vos crédits pour envoyer' : 'Envoie via Resend (@afroboosteur.com) et WhatsApp'}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            
            {/* === EMAIL VIA RESEND === */}
            <div className="p-4 rounded-xl bg-blue-900/20 border border-blue-500/30">
              <h4 className="text-white font-semibold mb-3 flex items-center gap-2">
                📧 Email (Resend)
                <span className="ml-auto text-xs text-green-400">✓ Actif</span>
              </h4>
              
              {/* Barre de progression */}
              {emailSendingProgress && (
                <div className="mb-3">
                  <div className="flex justify-between text-xs text-white/80 mb-1">
                    <span>Envoi en cours...</span>
                    <span>{emailSendingProgress.current}/{emailSendingProgress.total}</span>
                  </div>
                  <div className="w-full bg-gray-700 rounded-full h-2">
                    <div 
                      className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${(emailSendingProgress.current / emailSendingProgress.total) * 100}%` }}
                    />
                  </div>
                  {emailSendingProgress.name && (
                    <p className="text-xs text-blue-300 mt-1 truncate">→ {emailSendingProgress.name}</p>
                  )}
                </div>
              )}
              
              {/* Résultats d'envoi */}
              {emailSendingResults && !emailSendingProgress && (
                <div className="mb-3 p-2 rounded-lg bg-black/30">
                  <p className="text-sm font-semibold text-white">
                    ✅ {emailSendingResults.sent} envoyé(s)
                    {emailSendingResults.failed > 0 && (
                      <span className="text-red-400 ml-2">❌ {emailSendingResults.failed} échec(s)</span>
                    )}
                  </p>
                  <button 
                    type="button"
                    onClick={() => setEmailSendingResults(null)}
                    className="text-xs text-blue-400 mt-1"
                  >
                    Fermer
                  </button>
                </div>
              )}
              
              <p className="text-xs text-white/60 mb-3">
                {contactStats.withEmail} destinataire(s)
                <span className="text-green-400 ml-1">✓ Resend configuré</span>
              </p>
              
              {contactStats.withEmail > 0 ? (
                <div className="space-y-2">
                  <button 
                    type="button"
                    onClick={(e) => handleSendEmailCampaign(e)}
                    disabled={emailSendingProgress !== null}
                    className="w-full py-3 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-center font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    data-testid="send-email-campaign-btn"
                  >
                    {emailSendingProgress ? '⏳ Envoi...' : '🚀 Envoyer automatiquement'}
                  </button>
                  <a 
                    href={generateGroupedEmailLink()}
                    className="block w-full py-2 rounded-lg glass text-white text-center text-xs opacity-70 hover:opacity-100"
                  >
                    📧 Ouvrir client email (BCC)
                  </a>
                </div>
              ) : (
                <button disabled className="w-full py-3 rounded-lg bg-gray-600/50 text-gray-400 cursor-not-allowed">
                  Aucun email
                </button>
              )}
            </div>

            {/* === WHATSAPP AUTOMATIQUE (Twilio) === */}
            <div className="p-4 rounded-xl bg-green-900/20 border border-green-500/30">
              <h4 className="text-white font-semibold mb-3 flex items-center gap-2">
                📱 WhatsApp
                <button 
                  type="button"
                  onClick={() => setShowWhatsAppConfig(!showWhatsAppConfig)}
                  className="ml-auto text-xs text-green-400 hover:text-green-300"
                >
                  ⚙️ Config
                </button>
              </h4>
              
              {/* Barre de progression WhatsApp */}
              {whatsAppSendingProgress && (
                <div className="mb-3">
                  <div className="flex justify-between text-xs text-white/80 mb-1">
                    <span>Envoi en cours...</span>
                    <span>{whatsAppSendingProgress.current}/{whatsAppSendingProgress.total}</span>
                  </div>
                  <div className="w-full bg-gray-700 rounded-full h-2">
                    <div 
                      className="bg-green-500 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${(whatsAppSendingProgress.current / whatsAppSendingProgress.total) * 100}%` }}
                    />
                  </div>
                  {whatsAppSendingProgress.name && (
                    <p className="text-xs text-green-300 mt-1 truncate">→ {whatsAppSendingProgress.name}</p>
                  )}
                </div>
              )}
              
              {/* Résultats WhatsApp */}
              {whatsAppSendingResults && !whatsAppSendingProgress && (
                <div className="mb-3 p-2 rounded-lg bg-black/30">
                  <p className="text-sm font-semibold text-white">
                    ✅ {whatsAppSendingResults.sent} envoyé(s)
                    {whatsAppSendingResults.failed > 0 && (
                      <span className="text-red-400 ml-2">❌ {whatsAppSendingResults.failed} échec(s)</span>
                    )}
                  </p>
                  <button 
                    type="button"
                    onClick={() => setWhatsAppSendingResults(null)}
                    className="text-xs text-green-400 mt-1"
                  >
                    Fermer
                  </button>
                </div>
              )}
              
              <p className="text-xs text-white/60 mb-3">
                {contactStats.withPhone} destinataire(s)
                {isWhatsAppConfigured() ? (
                  <span className="text-green-400 ml-1">✓ Twilio</span>
                ) : (
                  <span className="text-yellow-400 ml-1">⚠️ Non configuré</span>
                )}
              </p>
              
              {contactStats.withPhone > 0 ? (
                <div className="space-y-2">
                  <button 
                    type="button"
                    onClick={(e) => handleSendWhatsAppCampaign(e)}
                    disabled={whatsAppSendingProgress !== null || !isWhatsAppConfigured()}
                    className="w-full py-2 rounded-lg bg-green-600 hover:bg-green-700 text-white text-center font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                    data-testid="send-whatsapp-campaign-btn"
                  >
                    {whatsAppSendingProgress ? '⏳ Envoi...' : '🚀 Auto (Twilio)'}
                  </button>
                  
                  {/* Mode manuel conservé */}
                  <div className="border-t border-green-500/20 pt-2 mt-2">
                    <p className="text-xs text-white/40 mb-1">Mode manuel:</p>
                    <p className="text-xs text-white/60 mb-1">
                      {currentWhatsAppIndex + 1}/{contactStats.withPhone}
                      {getCurrentWhatsAppContact() && (
                        <span className="text-green-300 ml-1">→ {getCurrentWhatsAppContact()?.name}</span>
                      )}
                    </p>
                    <div className="flex gap-1">
                      <button 
                        type="button"
                        onClick={prevWhatsAppContact}
                        disabled={currentWhatsAppIndex === 0}
                        className="flex-1 py-1 rounded glass text-white text-xs disabled:opacity-30"
                      >
                        ←
                      </button>
                      <a 
                        href={getCurrentWhatsAppContact() ? generateWhatsAppLink(
                          getCurrentWhatsAppContact()?.phone,
                          newCampaign.message,
                          newCampaign.mediaUrl,
                          getCurrentWhatsAppContact()?.name
                        ) : '#'}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-2 py-1 px-2 rounded bg-green-700 text-white text-xs text-center"
                      >
                        Ouvrir
                      </a>
                      <button 
                        type="button"
                        onClick={nextWhatsAppContact}
                        disabled={currentWhatsAppIndex >= contactStats.withPhone - 1}
                        className="flex-1 py-1 rounded glass text-white text-xs disabled:opacity-30"
                      >
                        →
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <button disabled className="w-full py-3 rounded-lg bg-gray-600/50 text-gray-400 cursor-not-allowed">
                  Aucun numéro
                </button>
              )}
            </div>

            {/* === INSTAGRAM DM === */}
            <div className="p-4 rounded-xl bg-purple-900/20 border border-purple-500/30">
              <h4 className="text-white font-semibold mb-3 flex items-center gap-2">
                📸 Instagram DM
              </h4>
              <div className="mb-3">
                <label className="text-xs text-white/60 block mb-1">Profil Instagram</label>
                <input 
                  type="text" 
                  value={instagramProfile}
                  onChange={e => setInstagramProfile(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg neon-input text-sm"
                  placeholder="username"
                />
              </div>
              <button 
                type="button"
                onClick={copyMessageForInstagram}
                className={`w-full py-2 rounded-lg ${messageCopied ? 'bg-green-600' : 'bg-purple-600 hover:bg-purple-700'} text-white text-sm font-medium mb-2 transition-all`}
              >
                {messageCopied ? '✓ Copié !' : '📋 Copier le message'}
              </button>
              <a 
                href={`https://instagram.com/${instagramProfile}`}
                target="_blank"
                rel="noopener noreferrer"
                className="block w-full py-2 rounded-lg glass text-white text-center text-sm hover:bg-purple-500/20 transition-all"
              >
                📸 Ouvrir Instagram
              </a>
            </div>

          </div>
        </div>
      )}

      {/* === SECTION TEST EMAIL RESEND === */}
      <div className="mb-8 p-5 rounded-xl glass border-2 border-blue-500/50">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-white font-semibold flex items-center gap-2">
            📧 Test Email (Resend)
            <span className="text-green-400 text-xs ml-2">✓ Configuré</span>
          </h3>
        </div>
        
        <p className="text-xs text-white/60 mb-4">
          Les emails sont envoyés depuis <strong>notifications@afroboosteur.com</strong> via Resend.
        </p>

        {/* v9.3.8: Fix mobile - flex-wrap pour que le bouton Tester s'adapte */}
        <div className="flex flex-wrap items-center gap-2">
          <input 
            type="email"
            value={testEmailAddress}
            onChange={e => setTestEmailAddress(e.target.value)}
            className="flex-1 min-w-0 px-3 py-2 rounded-lg neon-input text-sm"
            placeholder="Email de test..."
            data-testid="test-email-input"
          />
          <button 
            type="button"
            onClick={(e) => handleTestEmail(e)}
            disabled={testEmailStatus === 'sending'}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex-shrink-0 ${
              testEmailStatus === 'success' ? 'bg-green-600' :
              testEmailStatus === 'error' ? 'bg-red-600' :
              testEmailStatus === 'sending' ? 'bg-yellow-600' :
              'bg-purple-600 hover:bg-purple-700'
            } text-white disabled:opacity-50`}
            data-testid="test-email-btn"
          >
            {testEmailStatus === 'sending' ? '⏳...' :
             testEmailStatus === 'success' ? '✅ Envoyé!' :
             testEmailStatus === 'error' ? '❌ Erreur' :
             '🧪 Tester'}
          </button>
        </div>
      </div>

      {/* === PANNEAU DE CONFIGURATION WHATSAPP API === */}
      {showWhatsAppConfig && (
        <div className="mb-8 p-5 rounded-xl glass border-2 border-green-500/50">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-white font-semibold flex items-center gap-2">
              ⚙️ Configuration WhatsApp API (Twilio)
            </h3>
            <button 
              type="button"
              onClick={() => setShowWhatsAppConfig(false)}
              className="text-white/60 hover:text-white"
            >
              ×
            </button>
          </div>
          
          <p className="text-xs text-white/60 mb-4">
            Créez un compte sur <a href="https://www.twilio.com" target="_blank" rel="noopener noreferrer" className="text-green-400 underline">twilio.com</a>, 
            activez WhatsApp Sandbox, puis ajoutez vos clés ci-dessous. 
            <a href="https://www.twilio.com/docs/whatsapp/sandbox" target="_blank" rel="noopener noreferrer" className="text-green-400 underline ml-1">Guide Sandbox</a>
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <div>
              <label className="block mb-1 text-white text-xs">Account SID</label>
              <input 
                type="text" 
                value={whatsAppConfig.accountSid}
                onChange={e => setWhatsAppConfig({...whatsAppConfig, accountSid: e.target.value})}
                className="w-full px-3 py-2 rounded-lg neon-input text-sm"
                placeholder="ACxxxxxxxxxxxxxxx"
              />
            </div>
            <div>
              <label className="block mb-1 text-white text-xs">Auth Token</label>
              <input 
                type="password" 
                value={whatsAppConfig.authToken}
                onChange={e => setWhatsAppConfig({...whatsAppConfig, authToken: e.target.value})}
                className="w-full px-3 py-2 rounded-lg neon-input text-sm"
                placeholder="••••••••••••••••"
              />
            </div>
            <div>
              <label className="block mb-1 text-white text-xs">From Number (Sandbox)</label>
              <input 
                type="text" 
                value={whatsAppConfig.fromNumber}
                onChange={e => setWhatsAppConfig({...whatsAppConfig, fromNumber: e.target.value})}
                className="w-full px-3 py-2 rounded-lg neon-input text-sm"
                placeholder="+14155238886"
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-3 items-center">
            <button 
              type="button"
              onClick={handleSaveWhatsAppConfig}
              className="px-4 py-2 rounded-lg bg-green-600 hover:bg-green-700 text-white text-sm font-medium"
            >
              💾 Sauvegarder
            </button>
            
            {/* Test WhatsApp - v9.3.8: Fix mobile avec flex-wrap */}
            <div className="flex flex-wrap items-center gap-2 flex-1">
              <input 
                type="tel"
                value={testWhatsAppNumber}
                onChange={e => setTestWhatsAppNumber(e.target.value)}
                className="flex-1 min-w-0 px-3 py-2 rounded-lg neon-input text-sm"
                placeholder="+41791234567"
              />
              <button 
                type="button"
                onClick={(e) => handleTestWhatsApp(e)}
                disabled={testWhatsAppStatus === 'sending' || !whatsAppConfig.accountSid}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex-shrink-0 ${
                  testWhatsAppStatus === 'success' ? 'bg-green-600' :
                  testWhatsAppStatus === 'error' ? 'bg-red-600' :
                  testWhatsAppStatus === 'sending' ? 'bg-yellow-600' :
                  'bg-purple-600 hover:bg-purple-700'
                } text-white disabled:opacity-50`}
                data-testid="test-whatsapp-btn"
              >
                {testWhatsAppStatus === 'sending' ? '⏳...' :
                 testWhatsAppStatus === 'success' ? '✅ Envoyé!' :
                 testWhatsAppStatus === 'error' ? '❌ Erreur' :
                 '🧪 Tester'}
              </button>
            </div>
          </div>

          <div className="mt-4 p-3 rounded-lg bg-green-900/20 border border-green-500/20">
            <p className="text-xs text-white/70">
              <strong>📋 Configuration Sandbox Twilio :</strong><br/>
              1. Allez sur <code className="text-green-400">console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn</code><br/>
              2. Envoyez "join &lt;code&gt;" au numéro sandbox depuis votre WhatsApp<br/>
              3. Utilisez le numéro sandbox comme "From Number": <code className="text-green-400">+14155238886</code>
            </p>
          </div>
        </div>
      )}

      {/* === PANNEAU AGENT IA WHATSAPP === */}
      <div className="mb-8 p-5 rounded-xl glass border-2 border-purple-500/50">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-white font-semibold flex items-center gap-2">
            🤖 Agent IA WhatsApp
            <span className={`text-xs px-2 py-0.5 rounded-full ${aiConfig.enabled ? 'bg-green-600' : 'bg-gray-600'}`}>
              {aiConfig.enabled ? '✓ Actif' : 'Inactif'}
            </span>
            {/* v9.3.8: Indicateur de sauvegarde automatique */}
            {aiConfigSaveStatus && (
              <span 
                className="text-xs px-2 py-0.5 rounded-full"
                style={{
                  background: aiConfigSaveStatus === 'saved' ? 'rgba(34, 197, 94, 0.2)' : 
                             aiConfigSaveStatus === 'error' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(147, 51, 234, 0.2)',
                  color: aiConfigSaveStatus === 'saved' ? '#22c55e' : 
                         aiConfigSaveStatus === 'error' ? '#ef4444' : '#a855f7'
                }}
              >
                {aiConfigSaveStatus === 'saving' && '⏳'}
                {aiConfigSaveStatus === 'saved' && '✓ Sauvegardé'}
                {aiConfigSaveStatus === 'error' && '⚠️ Erreur'}
              </span>
            )}
          </h3>
          <button 
            type="button"
            onClick={() => setShowAIConfig(!showAIConfig)}
            className="text-xs text-purple-400 hover:text-purple-300"
          >
            {showAIConfig ? '▲ Réduire' : '▼ Configurer'}
          </button>
        </div>

        {/* Logs rapides - toujours visible */}
        {aiLogs.length > 0 && (
          <div className="mb-4 p-3 rounded-lg bg-black/30 border border-purple-500/20">
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs text-white/60">📝 Dernières réponses IA</span>
              <button 
                type="button"
                onClick={handleClearAILogs}
                className="text-xs text-red-400 hover:text-red-300"
              >
                🗑️ Effacer
              </button>
            </div>
            <div className="space-y-1 max-h-24 overflow-y-auto">
              {aiLogs.slice(0, 3).map((log, idx) => (
                <div key={idx} className="text-xs flex items-center gap-2">
                  <span className="text-purple-400">
                    {new Date(log.timestamp).toLocaleTimeString('fr-FR', {hour: '2-digit', minute: '2-digit'})}
                  </span>
                  <span className="text-white/80">{log.clientName || log.fromPhone}</span>
                  <span className="text-green-400 truncate flex-1">→ {log.aiResponse?.slice(0, 50)}...</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {showAIConfig && (
          <div className="space-y-4">
            <p className="text-xs text-white/60 mb-4">
              L'Agent IA répond automatiquement aux messages WhatsApp entrants via le webhook Twilio.
              Il utilise le contexte des réservations pour personnaliser les réponses.
            </p>

            {/* Toggle Enabled */}
            <div className="flex items-center justify-between p-3 rounded-lg bg-purple-900/20 border border-purple-500/30">
              <div>
                <span className="text-white font-medium">Activer l'Agent IA</span>
                <p className="text-xs text-white/50">Répond automatiquement aux messages WhatsApp</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input 
                  type="checkbox" 
                  checked={aiConfig.enabled}
                  onChange={e => setAiConfig({...aiConfig, enabled: e.target.checked})}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-purple-600"></div>
              </label>
            </div>

            {/* System Prompt */}
            <div>
              <label className="block mb-2 text-white text-sm">🎯 Prompt Système (Personnalité de l'IA)</label>
              <textarea 
                value={aiConfig.systemPrompt}
                onChange={e => setAiConfig({...aiConfig, systemPrompt: e.target.value})}
                className="w-full px-4 py-3 rounded-lg neon-input text-sm"
                rows={6}
                placeholder="Décrivez la personnalité et le rôle de l'IA..."
              />
            </div>

            {/* Lien de paiement Twint */}
            <div className="p-4 rounded-lg bg-green-900/20 border border-green-500/30">
              <label className="block mb-2 text-white text-sm">💳 Lien de paiement Twint</label>
              <input 
                type="url"
                value={aiConfig.twintPaymentUrl || ''}
                onChange={e => setAiConfig({...aiConfig, twintPaymentUrl: e.target.value})}
                className="w-full px-4 py-3 rounded-lg neon-input text-sm"
                placeholder="https://twint.ch/pay/... ou votre lien de paiement"
                data-testid="twint-payment-url-input"
              />
              <p className="text-xs mt-2 text-white/50">
                L'IA proposera ce lien aux clients souhaitant acheter un produit ou un cours.
                {!aiConfig.twintPaymentUrl && <span className="text-yellow-400"> ⚠️ Non configuré : l'IA redirigera vers le coach.</span>}
              </p>
            </div>

            {/* 🚨 PROMPT CAMPAGNE - PRIORITÉ ABSOLUE */}
            <div className="p-4 rounded-lg bg-red-900/20 border border-red-500/50">
              <label className="block mb-2 text-white text-sm font-bold">
                🚨 Prompt Campagne <span className="text-red-400">(PRIORITÉ ABSOLUE)</span>
              </label>
              <textarea 
                value={aiConfig.campaignPrompt || ''}
                onChange={e => setAiConfig({...aiConfig, campaignPrompt: e.target.value})}
                className="w-full px-4 py-3 rounded-lg neon-input text-sm h-32"
                placeholder="Ex: Parle uniquement en majuscules. / Propose toujours l'essai gratuit du Mercredi. / Mets en avant l'offre spéciale été à 50 CHF."
                data-testid="campaign-prompt-input"
              />
              <p className="text-xs mt-2 text-white/50">
                <span className="text-red-400 font-medium">⚠️ Ce prompt ÉCRASE les règles par défaut de l'IA.</span><br/>
                Utilisez-le pour des consignes spéciales de campagne (ex: "Réponds en majuscules", "Propose l'essai gratuit").
                L'IA suivra ces instructions même si elles contredisent les autres règles.
              </p>
            </div>

            {/* Model Selection */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block mb-1 text-white text-xs">Provider</label>
                <select 
                  value={aiConfig.provider}
                  onChange={e => setAiConfig({...aiConfig, provider: e.target.value})}
                  className="w-full px-3 py-2 rounded-lg neon-input text-sm"
                >
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="google">Google</option>
                </select>
              </div>
              <div>
                <label className="block mb-1 text-white text-xs">Modèle</label>
                <select 
                  value={aiConfig.model}
                  onChange={e => setAiConfig({...aiConfig, model: e.target.value})}
                  className="w-full px-3 py-2 rounded-lg neon-input text-sm"
                >
                  <option value="gpt-4o-mini">GPT-4o Mini (rapide)</option>
                  <option value="gpt-4o">GPT-4o (puissant)</option>
                  <option value="claude-3-haiku-20240307">Claude 3 Haiku</option>
                  <option value="gemini-1.5-flash">Gemini 1.5 Flash</option>
                </select>
              </div>
            </div>

            {/* Webhook URL */}
            <div className="p-3 rounded-lg bg-blue-900/20 border border-blue-500/20">
              <p className="text-xs text-white/70">
                <strong>🔗 Webhook Twilio :</strong><br/>
                Configurez cette URL dans votre console Twilio → Messaging → WhatsApp Sandbox → "When a message comes in":<br/>
                <code className="text-blue-400 block mt-1 bg-black/30 px-2 py-1 rounded">
                  {API}/webhook/whatsapp
                </code>
              </p>
            </div>

            {/* Test Area */}
            <div className="p-3 rounded-lg bg-purple-900/20 border border-purple-500/20">
              <p className="text-xs text-white/70 mb-2"><strong>🧪 Tester l'IA</strong></p>
              {/* v9.3.8: Fix mobile avec flex-wrap */}
              <div className="flex flex-wrap gap-2">
                <input 
                  type="text"
                  value={aiTestMessage}
                  onChange={e => setAiTestMessage(e.target.value)}
                  className="flex-1 min-w-0 px-3 py-2 rounded-lg neon-input text-sm"
                  placeholder="Ex: Quels sont les horaires des cours ?"
                />
                <button 
                  type="button"
                  onClick={handleTestAI}
                  disabled={aiTestLoading}
                  className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-sm disabled:opacity-50 flex-shrink-0"
                >
                  {aiTestLoading ? '⏳' : '🤖 Tester'}
                </button>
              </div>
              {aiTestResponse && (
                <div className={`mt-2 p-2 rounded text-sm ${aiTestResponse.success ? 'bg-green-900/30 text-green-300' : 'bg-red-900/30 text-red-300'}`}>
                  {aiTestResponse.success ? (
                    <>
                      <p className="font-medium">Réponse IA ({aiTestResponse.responseTime?.toFixed(2)}s):</p>
                      <p className="text-white/90 mt-1">{aiTestResponse.response}</p>
                    </>
                  ) : (
                    <p>❌ Erreur: {aiTestResponse.error}</p>
                  )}
                </div>
              )}
            </div>

            <button 
              type="button"
              onClick={handleSaveAIConfig}
              className="w-full py-3 rounded-lg bg-purple-600 hover:bg-purple-700 text-white font-medium"
            >
              💾 Sauvegarder la configuration IA
            </button>
          </div>
        )}
      </div>
      </div>{/* Fin section canaux externes masquée */}
      
      {/* Bouton pour afficher/masquer les canaux externes */}
      <div className="mb-4">
        <button 
          type="button"
          onClick={() => setExternalChannelsExpanded(!externalChannelsExpanded)}
          className="px-4 py-2 rounded-lg text-sm font-medium glass text-gray-400 hover:text-white border border-gray-500/30 hover:border-purple-500/30 transition-all"
        >
          {externalChannelsExpanded ? '▼ Masquer canaux externes' : '▶ Afficher canaux externes (WhatsApp, Email, Instagram...)'}
        </button>
      </div>

      {/* New Campaign Form */}
      <form onSubmit={createCampaign} className="mb-8 p-5 rounded-xl glass">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-white font-semibold">
            {editingCampaignId ? '✏️ Modifier la Campagne' : 'Nouvelle Campagne'}
          </h3>
          {editingCampaignId && (
            <button 
              type="button" 
              onClick={cancelEditCampaign}
              className="px-3 py-1 rounded text-xs bg-gray-600 hover:bg-gray-700 text-white"
            >
              ❌ Annuler
            </button>
          )}
        </div>
        
        {/* Campaign Name */}
        <div className="mb-4">
          <label className="block mb-2 text-white text-sm">Nom de la campagne</label>
          <input type="text" required value={newCampaign.name} onChange={e => setNewCampaign({...newCampaign, name: e.target.value})}
            className="w-full px-4 py-3 rounded-lg neon-input" placeholder="Ex: Promo Noël 2024" />
        </div>
        
        {/* === SÉLECTEUR DE DESTINATAIRE UNIFIÉ (PRINCIPAL) === */}
        <div className="mb-4 p-4 rounded-lg border border-green-500/40 bg-green-900/20" data-testid="unified-recipient-selector">
          <div className="flex items-center justify-between mb-3">
            <label className="text-green-400 text-sm font-medium">📍 Destinataires ({selectedRecipients.length})</label>
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400">
                {activeConversations.filter(c => c.type === 'group').length} groupes • {activeConversations.filter(c => c.type === 'user').length} utilisateurs
              </span>
              <button type="button"
                onClick={() => {
                  // Anti-doublons: filtrer ceux déjà dans le panier
                  const existingIds = new Set(selectedRecipients.map(r => r.id));
                  const newItems = activeConversations
                    .filter(c => !existingIds.has(c.conversation_id))
                    .map(c => ({id: c.conversation_id, name: c.name || 'Sans nom', type: c.type}));
                  if (newItems.length > 0) {
                    setSelectedRecipients(prev => [...prev, ...newItems]);
                    showCampaignToast(`✅ ${newItems.length} destinataires ajoutés au panier`, 'success');
                  } else {
                    showCampaignToast('ℹ️ Tous les destinataires sont déjà dans le panier', 'info');
                  }
                }}
                className="px-2 py-1 rounded text-xs bg-purple-600/30 hover:bg-purple-600/50 text-purple-400"
                data-testid="add-all-btn"
              >+ Tous ({activeConversations.length})</button>
              <button type="button"
                onClick={async () => {
                  try {
                    const axios = (await import('axios')).default;
                    const res = await axios.get(`${API}/conversations/active`);
                    if (res.data.success) {
                      setActiveConversations(res.data.conversations || []);
                      showCampaignToast(`Liste actualisée : ${res.data.total} conversation(s)`, 'info');
                    }
                  } catch (err) { showCampaignToast('Erreur de synchronisation', 'error'); }
                }}
                className="px-2 py-1 rounded text-xs bg-green-600/30 hover:bg-green-600/50 text-green-400"
                data-testid="refresh-conversations-btn"
              >🔄</button>
            </div>
          </div>
          
          {/* PANIER DE TAGS */}
          {selectedRecipients.length > 0 && (
            <div className="mb-3 p-3 rounded-lg bg-green-900/20 border border-green-500/30" data-testid="recipient-basket">
              <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto">
                {selectedRecipients.map(r => (
                  <span key={r.id} className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${r.type === 'group' ? 'bg-purple-600/50 text-purple-200 border border-purple-400/30' : 'bg-blue-600/50 text-blue-200 border border-blue-400/30'}`}
                    data-testid={`tag-${r.id}`}>
                    <span className="text-sm">{r.type === 'group' ? '👥' : '👤'}</span>
                    <span className="truncate max-w-[120px]">{(r.name || 'Sans nom').replace(/^👤 |^👥 /, '').substring(0, 20)}</span>
                    <button type="button" onClick={() => setSelectedRecipients(prev => prev.filter(x => x.id !== r.id))}
                      className="ml-1 hover:text-red-400 text-sm font-bold" title="Retirer">×</button>
                  </span>
                ))}
              </div>
              <div className="flex justify-between items-center mt-3 pt-2 border-t border-green-500/20">
                <span className="text-xs text-green-400 font-medium">
                  ✅ Prêt à envoyer à {selectedRecipients.length} destinataire(s) 
                  ({selectedRecipients.filter(r => r.type === 'group').length} 👥, {selectedRecipients.filter(r => r.type === 'user').length} 👤)
                </span>
                <button type="button" onClick={() => { setSelectedRecipients([]); showCampaignToast('Panier vidé', 'info'); }} 
                  className="px-2 py-1 rounded text-xs bg-red-600/30 hover:bg-red-600/50 text-red-400 font-medium"
                  data-testid="clear-basket-btn">
                  🗑️ Vider
                </button>
              </div>
            </div>
          )}
          
          {/* Champ de recherche */}
          <div className="relative">
            <input type="text" placeholder="🔍 Rechercher un groupe ou utilisateur (ex: Lion, Marie...)"
              value={conversationSearch}
              onChange={(e) => { setConversationSearch(e.target.value); setShowConversationDropdown(true); }}
              onFocus={() => setShowConversationDropdown(true)}
              className="w-full px-4 py-3 rounded-lg neon-input text-sm"
              data-testid="recipient-search-input"
            />
            
            {/* Dropdown - Mobile optimized with max-height 80vh */}
            {showConversationDropdown && (
              <div 
                className="absolute z-50 w-full mt-1 rounded-lg bg-black/95 border border-green-500/30 shadow-xl flex flex-col"
                style={{ maxHeight: '80vh' }}
              >
                {/* === HEADER MOBILE avec bouton Fermer (icône filaire) === */}
                <div className="flex items-center justify-between p-3 border-b border-green-500/20 sticky top-0 bg-black/95 z-10">
                  <span className="text-sm text-green-400 font-medium">
                    📍 Sélectionner des destinataires
                  </span>
                  <button 
                    type="button"
                    onClick={() => setShowConversationDropdown(false)}
                    className="rounded-lg hover:bg-white/10 text-gray-400 hover:text-white transition-colors flex items-center justify-center"
                    style={{ minWidth: '44px', minHeight: '44px' }} /* Min 44px pour accessibilité mobile */
                    title="Fermer"
                    data-testid="close-recipient-dropdown"
                  >
                    {/* Icône X filaire - plus grand pour mobile */}
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                      <line x1="18" y1="6" x2="6" y2="18"></line>
                      <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                  </button>
                </div>
                
                {/* === CONTENU SCROLLABLE === */}
                <div className="overflow-y-auto flex-1" style={{ maxHeight: 'calc(80vh - 120px)' }}>
                  {/* Groupes */}
                  {activeConversations.filter(c => c.type === 'group' && (conversationSearch === '' || (c.name || '').toLowerCase().includes(conversationSearch.toLowerCase())) && !selectedRecipients.find(r => r.id === c.conversation_id)).length > 0 && (
                    <div className="p-2 border-b border-green-500/20">
                      <p className="text-xs text-purple-400 font-semibold mb-1 px-2">👥 GROUPES</p>
                      {activeConversations.filter(c => c.type === 'group' && (conversationSearch === '' || (c.name || '').toLowerCase().includes(conversationSearch.toLowerCase())) && !selectedRecipients.find(r => r.id === c.conversation_id)).map(conv => (
                        <button key={conv.conversation_id} type="button"
                          onClick={() => {
                            setSelectedRecipients(prev => [...prev, {id: conv.conversation_id, name: conv.name || 'Groupe', type: 'group'}]);
                            setConversationSearch('');
                            showCampaignToast(`✅ "${conv.name || 'Groupe'}" ajouté au panier`, 'success');
                          }}
                          className="w-full text-left px-3 py-2 rounded hover:bg-purple-600/30 text-white text-sm flex items-center gap-2">
                          <span>👥</span><span>{conv.name || 'Groupe'}</span>
                        </button>
                      ))}
                    </div>
                  )}
                  {/* Utilisateurs */}
                  {activeConversations.filter(c => c.type === 'user' && (conversationSearch === '' || (c.name || '').toLowerCase().includes(conversationSearch.toLowerCase())) && !selectedRecipients.find(r => r.id === c.conversation_id)).length > 0 && (
                    <div className="p-2">
                      <p className="text-xs text-blue-400 font-semibold mb-1 px-2">👤 UTILISATEURS</p>
                      {activeConversations.filter(c => c.type === 'user' && (conversationSearch === '' || (c.name || '').toLowerCase().includes(conversationSearch.toLowerCase())) && !selectedRecipients.find(r => r.id === c.conversation_id)).slice(0, 15).map(conv => (
                        <button key={conv.conversation_id} type="button"
                          onClick={() => {
                            setSelectedRecipients(prev => [...prev, {id: conv.conversation_id, name: conv.name || 'Utilisateur', type: 'user'}]);
                            setConversationSearch('');
                            showCampaignToast(`✅ "${conv.name || 'Utilisateur'}" ajouté au panier`, 'success');
                          }}
                          className="w-full text-left px-3 py-2 rounded hover:bg-blue-600/30 text-white text-sm flex items-center gap-2">
                          <span>👤</span><span className="truncate">{conv.name || 'Utilisateur'}</span>
                        </button>
                      ))}
                    </div>
                  )}
                  {activeConversations.filter(c => (conversationSearch === '' || (c.name || '').toLowerCase().includes(conversationSearch.toLowerCase())) && !selectedRecipients.find(r => r.id === c.conversation_id)).length === 0 && (
                    <p className="text-center py-4 text-gray-500 text-sm">{selectedRecipients.length > 0 ? 'Tous les résultats sont déjà dans le panier' : `Aucun résultat pour "${conversationSearch}"`}</p>
                  )}
                </div>
                
                {/* === FOOTER MOBILE avec bouton Valider (icône filaire) === */}
                <div className="p-3 border-t border-green-500/20 sticky bottom-0 bg-black/95 z-10">
                  <button 
                    type="button"
                    onClick={() => {
                      setShowConversationDropdown(false);
                      if (selectedRecipients.length > 0) {
                        showCampaignToast(`✅ ${selectedRecipients.length} destinataire(s) sélectionné(s)`, 'success');
                      }
                    }}
                    className="w-full py-2.5 rounded-lg bg-green-600 hover:bg-green-700 text-white text-sm font-medium flex items-center justify-center gap-2 transition-colors"
                    data-testid="validate-recipients-btn"
                  >
                    {/* Icône Check filaire */}
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                    Valider la sélection ({selectedRecipients.length})
                  </button>
                </div>
              </div>
            )}
          </div>
          
          {selectedRecipients.length === 0 && (
            <p className="text-xs text-yellow-400 mt-2">⚠️ Ajoutez au moins un destinataire pour créer la campagne.</p>
          )}
        </div>
        
        {/* === v11: TRIPLE CASE - SYSTEM PROMPT + OBJECTIF + MESSAGE === */}
        {/* Case 0: System Prompt (Instructions IA spécifiques à cette campagne) */}
        <div className="mb-4 p-4 rounded-xl glass border border-purple-500/30">
          <div className="flex items-center justify-between mb-2">
            <label className="text-white text-sm font-medium flex items-center gap-2">
              🧠 Prompt Système
              <span className="text-xs text-purple-400 font-normal">(instructions IA pour cette campagne)</span>
            </label>
            {newCampaign.systemPrompt && (
              <span className="text-xs text-green-400">✓ Personnalisé</span>
            )}
          </div>
          <textarea
            value={newCampaign.systemPrompt || ''}
            onChange={e => setNewCampaign(prev => ({ ...prev, systemPrompt: e.target.value }))}
            className="w-full px-4 py-3 rounded-lg neon-input text-sm"
            rows={3}
            placeholder="Ex: Tu es un coach Afrobeat motivant. Utilise un ton jeune et dynamique. Mentionne toujours les casques silencieux."
            data-testid="campaign-system-prompt"
          />
          <p className="text-xs text-white/50 mt-1">
            Instructions système pour l'IA de cette campagne. Si vide, le prompt global sera utilisé.
          </p>
        </div>

        {/* Case 1: Objectif/Prompt de description (persisté dans la campagne) */}
        <div className="mb-4 p-4 rounded-xl glass border border-yellow-500/30">
          <div className="flex items-center justify-between mb-2">
            <label className="text-white text-sm font-medium flex items-center gap-2">
              🎯 Objectif de la campagne
              <span className="text-xs text-yellow-400 font-normal">(pour l'IA)</span>
            </label>
          </div>
          <textarea
            value={campaignGoal}
            onChange={e => setCampaignGoal(e.target.value)}
            className="w-full px-4 py-3 rounded-lg neon-input text-sm"
            rows={2}
            placeholder="Ex: Ton motivant pour le cours de dimanche. / Relance clients inactifs avec promo -20%."
            data-testid="campaign-goal-input"
          />
          <p className="text-xs text-white/50 mt-1">
            Décrivez l'objectif de votre message. L'IA utilisera ce prompt pour générer des suggestions. Sauvegardé avec la campagne.
          </p>
        </div>
        
        {/* Case 2: Message avec bouton IA */}
        <div className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <label className="text-white text-sm font-medium">📝 Message final</label>
            <button
              type="button"
              onClick={generateAiSuggestions}
              disabled={aiSuggestionsLoading}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
              style={{
                background: aiSuggestionsLoading ? 'rgba(147, 51, 234, 0.2)' : 'linear-gradient(135deg, #9333ea, #6366f1)',
                color: '#fff',
                opacity: aiSuggestionsLoading ? 0.7 : 1
              }}
              data-testid="ai-suggest-btn"
            >
              {aiSuggestionsLoading ? (
                <>⏳ Génération...</>
              ) : (
                <>🤖 Suggérer avec l'IA</>
              )}
            </button>
          </div>
          
          <textarea 
            required 
            value={newCampaign.message} 
            onChange={e => setNewCampaign({...newCampaign, message: e.target.value})}
            className="w-full px-4 py-3 rounded-lg neon-input" 
            rows={4}
            placeholder="Salut {prénom} ! 🎉&#10;&#10;Profite de notre offre spéciale..."
            data-testid="campaign-message-input"
          />
          <p className="text-xs text-purple-400 mt-1">Variables disponibles: {'{prénom}'} - sera remplacé par le nom du contact</p>
          
          {/* === v9.4.1: Panneau des suggestions IA === */}
          {showAiSuggestions && (
            <div className="mt-3 p-4 rounded-lg bg-purple-900/30 border border-purple-500/40">
              <div className="flex items-center justify-between mb-3">
                <h5 className="text-white text-sm font-medium flex items-center gap-2">
                  ✨ Suggestions IA
                  {aiSuggestions.length > 0 && (
                    <span className="text-xs text-purple-400">({aiSuggestions.length} variantes)</span>
                  )}
                </h5>
                <button
                  type="button"
                  onClick={() => setShowAiSuggestions(false)}
                  className="text-white/50 hover:text-white text-sm"
                >
                  ✕
                </button>
              </div>
              
              {aiSuggestionsLoading ? (
                <div className="flex items-center justify-center py-6">
                  <div className="animate-spin rounded-full h-8 w-8 border-2 border-purple-500 border-t-transparent"></div>
                  <span className="ml-3 text-white/70 text-sm">L'IA génère des suggestions...</span>
                </div>
              ) : aiSuggestions.length > 0 ? (
                <div className="space-y-3">
                  {aiSuggestions.map((suggestion, idx) => (
                    <div 
                      key={idx}
                      className="p-3 rounded-lg bg-black/40 border border-purple-500/20 hover:border-purple-500/50 transition-all cursor-pointer"
                      onClick={() => insertSuggestion(suggestion.text)}
                      data-testid={`ai-suggestion-${idx}`}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          suggestion.type === 'Promo' ? 'bg-green-500/30 text-green-400' :
                          suggestion.type === 'Relance' ? 'bg-orange-500/30 text-orange-400' :
                          'bg-blue-500/30 text-blue-400'
                        }`}>
                          {suggestion.type === 'Promo' ? '🔥' : suggestion.type === 'Relance' ? '👋' : '📢'} {suggestion.type}
                        </span>
                        <span className="text-xs text-white/40">Cliquez pour insérer</span>
                      </div>
                      <p className="text-white/80 text-sm whitespace-pre-wrap">{suggestion.text}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-white/50 text-sm text-center py-4">
                  Aucune suggestion générée. Cliquez sur "Suggérer avec l'IA".
                </p>
              )}
            </div>
          )}
        </div>
        
        {/* === MÉDIA & CTA === */}
        <div className="mb-4 p-4 rounded-xl glass border border-purple-500/30">
          <h4 className="text-white font-semibold mb-3 flex items-center gap-2">
            📎 Joindre un média
            <span className="text-xs text-purple-400 font-normal">(optionnel)</span>
          </h4>
          
          {/* Sélecteur de média existant */}
          {mediaLinks && mediaLinks.length > 0 && (
            <div className="mb-4">
              <label className="block mb-2 text-white/70 text-sm">Vos médias enregistrés</label>
              <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto p-2 rounded-lg bg-black/30">
                {mediaLinks.map(media => {
                  const isSelected = newCampaign.mediaUrl === media.video_url || 
                                    (media.thumbnail && newCampaign.mediaUrl === media.thumbnail);
                  return (
                    <button
                      key={media.id}
                      type="button"
                      onClick={() => {
                        setNewCampaign(prev => ({
                          ...prev,
                          mediaUrl: media.video_url || media.thumbnail,
                          mediaTitle: media.title,
                          mediaCta: media.cta_type ? {
                            type: media.cta_type,
                            text: media.cta_text,
                            url: media.cta_link
                          } : null
                        }));
                      }}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg transition-all"
                      style={{
                        background: isSelected ? 'rgba(147, 51, 234, 0.4)' : 'rgba(255,255,255,0.1)',
                        border: isSelected ? '2px solid #9333ea' : '1px solid rgba(255,255,255,0.2)'
                      }}
                      data-testid={`select-media-${media.slug}`}
                    >
                      {media.thumbnail && (
                        <img 
                          src={media.thumbnail} 
                          alt="" 
                          className="w-10 h-10 rounded object-cover"
                          onError={(e) => e.target.style.display = 'none'}
                        />
                      )}
                      <span className="text-white text-xs truncate max-w-[100px]">{media.title}</span>
                      {media.cta_type && (
                        <span className="text-xs px-1.5 py-0.5 rounded bg-purple-500/30 text-purple-300">
                          {media.cta_type === 'RESERVER' ? '📅' : media.cta_type === 'OFFRE' ? '🛒' : '🔗'}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          
          {/* URL personnalisée */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="md:col-span-2">
              <label className="block mb-2 text-white/70 text-sm">Ou coller une URL (YouTube, Drive, Image)</label>
              <input 
                type="url" 
                value={newCampaign.mediaUrl} 
                onChange={e => {
                  const url = e.target.value;
                  setNewCampaign(prev => ({...prev, mediaUrl: url}));
                }}
                className="w-full px-4 py-3 rounded-lg neon-input" 
                placeholder="https://youtube.com/... ou https://drive.google.com/..." 
              />
              {/* Badge type de média détecté */}
              {newCampaign.mediaUrl && (() => {
                const parsed = parseMediaUrl(newCampaign.mediaUrl);
                return (
                  <div className="mt-2 flex items-center gap-2 text-xs">
                    <span className={`px-2 py-0.5 rounded-full ${
                      parsed.type === 'youtube' ? 'bg-red-500/30 text-red-400' :
                      parsed.type === 'drive' ? 'bg-blue-500/30 text-blue-400' :
                      parsed.type === 'image' ? 'bg-green-500/30 text-green-400' :
                      'bg-gray-500/30 text-gray-400'
                    }`}>
                      {parsed.type === 'youtube' ? '🎬 YouTube' :
                       parsed.type === 'drive' ? '📁 Drive' :
                       parsed.type === 'image' ? '🖼️ Image' :
                       '🔗 Lien'}
                    </span>
                  </div>
                );
              })()}
            </div>
            
            <div>
              <label className="block mb-2 text-white/70 text-sm">Format</label>
              <div className="flex gap-4 flex-wrap">
                <label className="flex items-center gap-2 text-white text-sm cursor-pointer">
                  <input type="radio" name="mediaFormat" checked={newCampaign.mediaFormat === "9:16"}
                    onChange={() => setNewCampaign({...newCampaign, mediaFormat: "9:16"})} />
                  9:16 (Stories)
                </label>
                <label className="flex items-center gap-2 text-white text-sm cursor-pointer">
                  <input type="radio" name="mediaFormat" checked={newCampaign.mediaFormat === "1:1"}
                    onChange={() => setNewCampaign({...newCampaign, mediaFormat: "1:1"})} />
                  1:1 (Carré)
                </label>
                <label className="flex items-center gap-2 text-white text-sm cursor-pointer">
                  <input type="radio" name="mediaFormat" checked={newCampaign.mediaFormat === "16:9"}
                    onChange={() => setNewCampaign({...newCampaign, mediaFormat: "16:9"})} />
                  16:9 (Post)
                </label>
              </div>
            </div>
          </div>
        </div>
        
        {/* Media Preview */}
        {newCampaign.mediaUrl && (
          <div className="mb-4">
            <p className="text-white text-sm mb-2">
              Aperçu ({newCampaign.mediaFormat}):
              {(newCampaign.mediaUrl.includes('/v/') || newCampaign.mediaUrl.includes('/api/share/')) && (
                <span className="ml-2 text-green-400 text-xs">✅ Lien interne</span>
              )}
              {newCampaign.ctaType && newCampaign.ctaType !== 'none' && (
                <span className="ml-2 text-purple-400 text-xs">+ CTA: {newCampaign.ctaText || newCampaign.ctaType}</span>
              )}
            </p>
            <div className="flex justify-center">
              <div style={{
                width: newCampaign.mediaFormat === "9:16" ? '150px' : newCampaign.mediaFormat === "1:1" ? '200px' : '280px',
                height: newCampaign.mediaFormat === "9:16" ? '267px' : newCampaign.mediaFormat === "1:1" ? '200px' : '158px',
                background: '#000', borderRadius: '8px', overflow: 'hidden',
                border: '1px solid rgba(139, 92, 246, 0.3)',
                display: 'flex', alignItems: 'center', justifyContent: 'center'
              }}>
                {/* v11: YouTube iframe embed au lieu de simple thumbnail */}
                {(() => {
                  const url = newCampaign.mediaUrl || '';
                  const ytMatch = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})/);
                  if (ytMatch) {
                    return (
                      <iframe
                        src={`https://www.youtube.com/embed/${ytMatch[1]}`}
                        title="YouTube Preview"
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                        allowFullScreen
                        style={{ width: '100%', height: '100%', border: 'none' }}
                      />
                    );
                  }
                  if (resolvedThumbnail) {
                    return (
                      <img
                        src={resolvedThumbnail}
                        alt="Preview"
                        referrerPolicy="no-referrer"
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        onError={(e) => {
                          e.target.style.display = 'none';
                          e.target.parentNode.innerHTML = '<span style="color:#888;font-size:12px;">Aperçu non disponible</span>';
                        }}
                      />
                    );
                  }
                  return <span style={{ color: '#888', fontSize: '12px' }}>Chargement...</span>;
                })()}
              </div>
            </div>
          </div>
        )}
        
        {/* === SECTION CTA (Bouton d'action) === */}
        <div className="mb-4 p-4 rounded-lg border border-purple-500/30 bg-purple-900/10">
          <label className="block mb-3 text-white text-sm font-medium">🔘 Bouton d'action (CTA)</label>
          
          {/* Type de CTA */}
          <div className="mb-3">
            <select 
              value={newCampaign.ctaType || 'none'}
              onChange={e => setNewCampaign({...newCampaign, ctaType: e.target.value, ctaText: '', ctaLink: ''})}
              className="w-full px-3 py-2 rounded-lg bg-gray-800/80 border border-gray-600 text-white text-sm focus:border-purple-500 focus:outline-none"
              data-testid="cta-type-select"
            >
              <option value="none">Aucun bouton</option>
              <option value="reserver">🗓️ Réserver (ouvre les cours)</option>
              <option value="offre">🎁 Offre (lien externe)</option>
              <option value="personnalise">✨ Personnalisé</option>
            </select>
          </div>
          
          {/* Texte du bouton (pour personnalisé ou modification) */}
          {newCampaign.ctaType && newCampaign.ctaType !== 'none' && (
            <div className="mb-3">
              <label className="block mb-1 text-gray-400 text-xs">Texte du bouton</label>
              <input 
                type="text"
                value={newCampaign.ctaText || ''}
                onChange={e => setNewCampaign({...newCampaign, ctaText: e.target.value})}
                placeholder={newCampaign.ctaType === 'reserver' ? 'RÉSERVER MA PLACE' : newCampaign.ctaType === 'offre' ? 'VOIR L\'OFFRE' : 'EN SAVOIR PLUS'}
                className="w-full px-3 py-2 rounded-lg bg-gray-800/80 border border-gray-600 text-white text-sm focus:border-purple-500 focus:outline-none"
                data-testid="cta-text-input"
              />
            </div>
          )}
          
          {/* URL du bouton (pour offre et personnalisé) */}
          {(newCampaign.ctaType === 'offre' || newCampaign.ctaType === 'personnalise') && (() => {
            // Validation de l'URL
            const urlValue = newCampaign.ctaLink || '';
            const isValidUrl = !urlValue || urlValue.startsWith('http://') || urlValue.startsWith('https://') || urlValue.startsWith('#');
            const isEmpty = urlValue.trim() === '';
            const showError = !isEmpty && !isValidUrl;
            
            return (
              <div className="mb-2">
                <label className="block mb-1 text-gray-400 text-xs">
                  Lien du bouton 
                  {showError && <span className="text-red-400 ml-2">⚠️ URL invalide</span>}
                </label>
                <input 
                  type="url"
                  value={urlValue}
                  onChange={e => setNewCampaign({...newCampaign, ctaLink: e.target.value})}
                  placeholder="https://..."
                  className={`w-full px-3 py-2 rounded-lg bg-gray-800/80 text-white text-sm focus:outline-none transition-colors ${
                    showError 
                      ? 'border-2 border-red-500 focus:border-red-400' 
                      : 'border border-gray-600 focus:border-purple-500'
                  }`}
                  data-testid="cta-link-input"
                />
                {showError && (
                  <p className="text-red-400 text-xs mt-1">
                    L'URL doit commencer par https:// ou http://
                  </p>
                )}
                {isEmpty && (newCampaign.ctaType === 'offre' || newCampaign.ctaType === 'personnalise') && (
                  <p className="text-yellow-400 text-xs mt-1">
                    ⚠️ Lien requis pour ce type de bouton
                  </p>
                )}
              </div>
            );
          })()}
          
          {/* Aperçu du bouton */}
          {newCampaign.ctaType && newCampaign.ctaType !== 'none' && (
            <div className="mt-3 flex justify-center">
              <div 
                style={{
                  padding: '10px 24px',
                  borderRadius: '25px',
                  background: newCampaign.ctaType === 'reserver' ? '#9333ea' : newCampaign.ctaType === 'offre' ? '#d91cd2' : '#6366f1',
                  color: '#fff',
                  fontWeight: '600',
                  fontSize: '13px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  boxShadow: '0 4px 15px rgba(147, 51, 234, 0.3)'
                }}
              >
                {newCampaign.ctaType === 'reserver' && '🗓️'}
                {newCampaign.ctaType === 'offre' && '🎁'}
                {newCampaign.ctaType === 'personnalise' && '✨'}
                {newCampaign.ctaText || (newCampaign.ctaType === 'reserver' ? 'RÉSERVER' : newCampaign.ctaType === 'offre' ? 'VOIR L\'OFFRE' : 'EN SAVOIR PLUS')}
              </div>
            </div>
          )}
        </div>
        
        {/* === PARAMÈTRES AVANCÉS (ACCORDÉON) === */}
        <div className="mb-4">
          <button 
            type="button"
            onClick={() => setExternalChannelsExpanded(!externalChannelsExpanded)}
            className="w-full text-left px-3 py-2 rounded-lg bg-gray-800/50 hover:bg-gray-700/50 text-gray-400 hover:text-white text-sm transition-all flex items-center justify-between"
          >
            <span>⚙️ Paramètres avancés (WhatsApp, Email, Groupe...)</span>
            <span>{externalChannelsExpanded ? '▼' : '▶'}</span>
          </button>
          
          {externalChannelsExpanded && (
            <div className="mt-3 p-4 rounded-lg border border-gray-600/30 bg-gray-800/20">
              <label className="block mb-2 text-white text-sm">Canaux d'envoi supplémentaires</label>
              <div className="flex flex-wrap gap-4 mb-3">
                <label className="flex items-center gap-2 text-white text-sm cursor-pointer">
                  <input type="checkbox" checked={newCampaign.channels.whatsapp}
                    onChange={e => setNewCampaign({...newCampaign, channels: {...newCampaign.channels, whatsapp: e.target.checked}})} />
                  📱 WhatsApp
                </label>
                <label className="flex items-center gap-2 text-white text-sm cursor-pointer">
                  <input type="checkbox" checked={newCampaign.channels.email}
                    onChange={e => setNewCampaign({...newCampaign, channels: {...newCampaign.channels, email: e.target.checked}})} />
                  📧 Email
                </label>
                <label className="flex items-center gap-2 text-white text-sm cursor-pointer">
                  <input type="checkbox" checked={newCampaign.channels.instagram}
                    onChange={e => setNewCampaign({...newCampaign, channels: {...newCampaign.channels, instagram: e.target.checked}})} />
                  📸 Instagram
                </label>
                <label className="flex items-center gap-2 text-white text-sm cursor-pointer">
                  <input type="checkbox" checked={newCampaign.channels.group || false}
                    onChange={e => setNewCampaign({...newCampaign, channels: {...newCampaign.channels, group: e.target.checked}})} />
                  💬 Groupe Afroboost
                </label>
              </div>
              
              {/* === SÉLECTEUR CRM POUR WHATSAPP/EMAIL === */}
              {(newCampaign.channels.whatsapp || newCampaign.channels.email) && (
                <div className="mb-3 p-3 rounded-lg border border-blue-500/30 bg-blue-900/20">
                  <label className="block mb-2 text-blue-400 text-xs font-medium">📇 Contacts CRM ({allContacts.length} au total)</label>
                  
                  {/* Mode de sélection */}
                  <div className="flex gap-4 mb-3">
                    <label className="flex items-center gap-2 text-white text-sm cursor-pointer">
                      <input type="radio" name="targetType" checked={newCampaign.targetType === "all"} 
                        onChange={() => setNewCampaign({...newCampaign, targetType: "all"})} />
                      ✅ Tous les contacts ({allContacts.length})
                    </label>
                    <label className="flex items-center gap-2 text-white text-sm cursor-pointer">
                      <input type="radio" name="targetType" checked={newCampaign.targetType === "selected"} 
                        onChange={() => setNewCampaign({...newCampaign, targetType: "selected"})} />
                      🎯 Sélection manuelle
                    </label>
                  </div>
                  
                  {/* Liste des contacts avec cases à cocher */}
                  {newCampaign.targetType === "selected" && (
                    <div className="border border-blue-500/20 rounded-lg p-2" style={{ maxHeight: '180px', overflowY: 'auto' }}>
                      <div className="flex items-center gap-2 mb-2">
                        <input type="text" placeholder="🔍 Filtrer les contacts..." value={contactSearchQuery}
                          onChange={e => setContactSearchQuery(e.target.value)}
                          className="flex-1 px-3 py-2 rounded-lg neon-input text-xs" />
                        <button type="button" onClick={toggleAllContacts} 
                          className="px-2 py-1 rounded-lg glass text-white text-xs whitespace-nowrap">
                          {selectedContactsForCampaign.length === allContacts.length ? '✗ Aucun' : '✓ Tous'}
                        </button>
                      </div>
                      <div className="space-y-1">
                        {filteredContacts.map(contact => (
                          <div key={contact.id} className="flex items-center gap-2 text-white text-xs hover:bg-blue-500/10 p-1 rounded">
                            <input type="checkbox" checked={selectedContactsForCampaign.includes(contact.id)}
                              onChange={() => toggleContactForCampaign(contact.id)} className="cursor-pointer" />
                            <span className="truncate flex-1">{contact.name ? contact.name.substring(0, 25) : 'Contact sans nom'}</span>
                            <span className="text-gray-500 truncate text-xs">({contact.email ? contact.email.substring(0, 20) : 'pas d\'email'})</span>
                          </div>
                        ))}
                      </div>
                      <p className="text-xs text-blue-400 mt-2">{selectedContactsForCampaign.length} contact(s) sélectionné(s)</p>
                    </div>
                  )}
                </div>
              )}
              
              {/* Sélecteur de groupe si canal groupe activé */}
              {newCampaign.channels.group && (
                <div className="p-3 rounded-lg border border-purple-500/30 bg-purple-900/20">
                  <label className="block mb-2 text-purple-400 text-xs">Groupe cible</label>
                  <select 
                    value={newCampaign.targetGroupId || 'community'}
                    onChange={e => setNewCampaign({...newCampaign, targetGroupId: e.target.value})}
                    className="w-full px-3 py-2 rounded-lg neon-input text-sm"
                  >
                    <option value="community">🌍 Communauté Générale</option>
                    <option value="vip">⭐ Groupe VIP</option>
                    <option value="promo">🎁 Offres Spéciales</option>
                  </select>
                  <p className="text-xs text-gray-400 mt-2">
                    💡 Le message sera envoyé par "💪 Coach Bassi" dans le chat de groupe.
                  </p>
                </div>
              )}
              
              <p className="text-xs text-gray-500 mt-3">
                ℹ️ Ces canaux nécessitent une configuration Twilio (WhatsApp) ou Resend (Email).
              </p>
            </div>
          )}
        </div>
        
        {/* Scheduling - Multi-date support */}
        <div className="mb-4">
          <label className="block mb-2 text-white text-sm">Programmation</label>
          <div className="flex flex-wrap gap-4 items-center mb-3">
            <label className="flex items-center gap-2 text-white text-sm cursor-pointer">
              <input type="radio" name="schedule" checked={newCampaign.scheduleSlots.length === 0}
                onChange={() => setNewCampaign({...newCampaign, scheduleSlots: []})} />
              Envoyer maintenant
            </label>
            <label className="flex items-center gap-2 text-white text-sm cursor-pointer">
              <input type="radio" name="schedule" checked={newCampaign.scheduleSlots.length > 0}
                onChange={addScheduleSlot} />
              Programmer (multi-dates)
            </label>
          </div>
          
          {/* Multi-date slots */}
          {newCampaign.scheduleSlots.length > 0 && (
            <div className="border border-purple-500/30 rounded-lg p-3 space-y-2">
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs text-purple-400">{newCampaign.scheduleSlots.length} date(s) programmée(s)</span>
                <button type="button" onClick={addScheduleSlot} 
                  className="px-3 py-1 rounded text-xs bg-purple-600 hover:bg-purple-700 text-white">
                  + Ajouter une date
                </button>
              </div>
              {newCampaign.scheduleSlots.map((slot, idx) => (
                <div key={idx} className="flex items-center gap-2 p-2 rounded-lg bg-black/30">
                  <span className="text-white text-xs w-6">#{idx + 1}</span>
                  <input type="date" value={slot.date} 
                    onChange={e => updateScheduleSlot(idx, 'date', e.target.value)}
                    className="px-3 py-2 rounded-lg neon-input text-sm flex-1" 
                    min={new Date().toISOString().split('T')[0]} />
                  <input type="time" value={slot.time}
                    onChange={e => updateScheduleSlot(idx, 'time', e.target.value)}
                    className="px-3 py-2 rounded-lg neon-input text-sm" />
                  <button type="button" onClick={() => removeScheduleSlot(idx)}
                    className="px-2 py-2 rounded text-xs bg-red-600/30 hover:bg-red-600/50 text-red-400"
                    title="Supprimer cette date">
                    ✕
                  </button>
                </div>
              ))}
              <p className="text-xs text-purple-400 mt-2">
                📅 Chaque date créera une ligne distincte avec le statut "Programmé"
              </p>
            </div>
          )}
        </div>
        
        {/* === RÉCAPITULATIF AVANT CRÉATION === */}
        {(newCampaign.name || selectedRecipients.length > 0 || (newCampaign.channels.whatsapp || newCampaign.channels.email)) && (
          <div className="mb-4 p-3 rounded-lg bg-gray-800/50 border border-gray-600/30">
            <p className="text-xs text-gray-400 mb-2">📋 Récapitulatif</p>
            <div className="flex flex-wrap gap-4 text-sm">
              {newCampaign.name && (
                <div className="flex items-center gap-2">
                  <span className="text-gray-500">Campagne:</span>
                  <span className="text-white font-medium">{newCampaign.name}</span>
                </div>
              )}
              
              {/* Panier de destinataires */}
              {selectedRecipients.length > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-gray-500">💌 Envoi prévu pour:</span>
                  <span className="text-green-400 font-medium">
                    {selectedRecipients.length} destinataire(s) ({selectedRecipients.filter(r => r.type === 'group').length} 👥, {selectedRecipients.filter(r => r.type === 'user').length} 👤)
                  </span>
                </div>
              )}
              
              {/* Contacts CRM pour WhatsApp/Email */}
              {(newCampaign.channels.whatsapp || newCampaign.channels.email) && (
                <div className="flex items-center gap-2">
                  <span className="text-gray-500">📇 CRM:</span>
                  <span className="text-blue-400 font-medium">
                    {newCampaign.targetType === "all" 
                      ? `✅ Tous (${allContacts.length})` 
                      : `🎯 ${selectedContactsForCampaign.length}/${allContacts.length} contact(s)`}
                  </span>
                </div>
              )}
              
              {/* Alerte si aucun destinataire */}
              {selectedRecipients.length === 0 && !(newCampaign.channels.whatsapp || newCampaign.channels.email) && !newCampaign.channels.group && (
                <div className="flex items-center gap-2">
                  <span className="text-yellow-500">⚠️ Panier vide - ajoutez au moins un destinataire</span>
                </div>
              )}
              
              {newCampaign.scheduleSlots.length > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-gray-500">Programmation:</span>
                  <span className="text-purple-400">{newCampaign.scheduleSlots.length} date(s)</span>
                </div>
              )}
            </div>
          </div>
        )}
        
        {/* v11: Estimation du coût en crédits */}
        {selectedRecipients.length > 0 && (
          <div className="mb-3 p-3 rounded-lg" style={{ background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)' }}>
            {isSuperAdmin ? (
              <div className="flex items-center justify-between">
                <span className="text-white/70 text-sm">Coût estimé</span>
                <span className="text-purple-400 font-bold text-sm">∞ Crédits illimités</span>
              </div>
            ) : (
              <div className="flex items-center justify-between">
                <span className="text-white/70 text-sm">Coût estimé</span>
                <span className="text-white font-bold text-sm">
                  {selectedRecipients.length * campaignCreditCost} crédit{selectedRecipients.length * campaignCreditCost > 1 ? 's' : ''}
                  <span className="text-white/50 font-normal ml-1">
                    ({selectedRecipients.length} contact{selectedRecipients.length > 1 ? 's' : ''} × {campaignCreditCost})
                  </span>
                </span>
              </div>
            )}
            {!isSuperAdmin && coachCredits !== null && coachCredits >= 0 && (
              <div className="mt-1 text-xs text-white/50">
                Solde actuel: {coachCredits} crédit{coachCredits > 1 ? 's' : ''}
                {coachCredits < selectedRecipients.length * campaignCreditCost && (
                  <span className="text-red-400 ml-2">⚠️ Insuffisant</span>
                )}
              </div>
            )}
          </div>
        )}

        {/* Bouton de soumission avec validation CTA */}
        {(() => {
          // Validation CTA URL
          const ctaNeedsUrl = newCampaign.ctaType === 'offre' || newCampaign.ctaType === 'personnalise';
          const ctaUrlValue = newCampaign.ctaLink || '';
          const ctaUrlValid = !ctaNeedsUrl || ctaUrlValue.trim() === '' || 
            ctaUrlValue.startsWith('http://') || ctaUrlValue.startsWith('https://') || ctaUrlValue.startsWith('#');
          const ctaUrlMissing = ctaNeedsUrl && ctaUrlValue.trim() === '';
          
          // Conditions de désactivation
          const noRecipients = selectedRecipients.length === 0 && !newCampaign.channels.whatsapp && !newCampaign.channels.email && !newCampaign.channels.group;
          const noMessage = !newCampaign.message.trim();
          const invalidCtaUrl = ctaNeedsUrl && !ctaUrlValid;
          const isDisabled = noRecipients || noMessage || invalidCtaUrl || ctaUrlMissing;
          
          return (
            <button type="submit" 
              className={`px-6 py-3 rounded-lg w-full md:w-auto font-medium transition-all ${
                editingCampaignId 
                  ? 'bg-green-600 hover:bg-green-700' 
                  : isDisabled
                    ? 'bg-gray-600 cursor-not-allowed opacity-60' 
                    : 'btn-primary'
              }`}
              disabled={isDisabled}
              data-testid="create-campaign-btn">
              {noMessage 
                ? '⚠️ Écrivez un message' 
                : noRecipients
                  ? '⚠️ Ajoutez des destinataires'
                  : invalidCtaUrl
                    ? '⚠️ URL du bouton invalide'
                    : ctaUrlMissing
                      ? '⚠️ Lien CTA requis'
                      : editingCampaignId 
                        ? '💾 Enregistrer' 
                        : `🚀 Créer (${selectedRecipients.length} dest.)`}
            </button>
          );
        })()}
      </form>
      
      {/* v11: Calendrier interactif des campagnes */}
      <CampaignCalendar
        campaigns={campaigns}
        onDayClick={(dateStr) => {
          // Pré-remplir un créneau de scheduling avec la date cliquée (sans scroll)
          setNewCampaign(prev => ({
            ...prev,
            scheduleSlots: [{ date: dateStr, time: '10:00' }]
          }));
          showCampaignToast(`📅 ${dateStr} sélectionné`, 'info');
        }}
        onCampaignClick={(campaign) => {
          // Ouvrir la campagne en mode édition
          if (typeof handleEditCampaign === 'function') {
            handleEditCampaign(campaign);
          }
        }}
      />

      {/* Campaign History */}
      <div>
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
          <h3 className="text-white font-semibold">📊 Historique des campagnes</h3>
          
          {/* Boutons de filtrage rapide */}
          <div className="flex gap-2" data-testid="campaign-history-filters">
            <button type="button" onClick={() => setCampaignHistoryFilter('all')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${campaignHistoryFilter === 'all' ? 'bg-purple-600 text-white' : 'bg-gray-700/50 text-gray-400 hover:text-white'}`}>
              Tout ({campaigns.length})
            </button>
            <button type="button" onClick={() => setCampaignHistoryFilter('groups')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${campaignHistoryFilter === 'groups' ? 'bg-purple-600 text-white' : 'bg-gray-700/50 text-gray-400 hover:text-white'}`}>
              👥 Groupes
            </button>
            <button type="button" onClick={() => setCampaignHistoryFilter('individuals')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${campaignHistoryFilter === 'individuals' ? 'bg-purple-600 text-white' : 'bg-gray-700/50 text-gray-400 hover:text-white'}`}>
              👤 Individuels
            </button>
          </div>
        </div>
        
        {/* Error Logs Panel - Shows if there are errors */}
        {campaignLogs.filter(l => l.type === 'error').length > 0 && (
          <div className="mb-4 p-3 rounded-lg bg-red-600/20 border border-red-500/30">
            <div className="flex items-center gap-2 mb-2">
              <span className="w-3 h-3 bg-red-500 rounded-full animate-pulse"></span>
              <span className="text-red-400 font-semibold text-sm">Erreurs récentes</span>
            </div>
            <div className="space-y-1 max-h-[100px] overflow-y-auto">
              {campaignLogs.filter(l => l.type === 'error').slice(0, 5).map(log => (
                <p key={log.id} className="text-xs text-red-300">{log.message}</p>
              ))}
            </div>
          </div>
        )}
        
        {/* Scrollable campaign history table with fixed max height */}
        <div className="overflow-x-auto overflow-y-auto rounded-lg border border-purple-500/20" 
             style={{ maxHeight: '400px', WebkitOverflowScrolling: 'touch' }}>
          <table className="w-full min-w-[700px]">
            <thead className="sticky top-0 bg-black z-10">
              <tr className="text-left text-white text-sm opacity-70 border-b border-purple-500/30">
                <th className="pb-3 pt-2 pr-4 bg-black">Campagne</th>
                <th className="pb-3 pt-2 pr-4 bg-black">Contacts</th>
                <th className="pb-3 pt-2 pr-4 bg-black">Canaux</th>
                <th className="pb-3 pt-2 pr-4 bg-black">Statut</th>
                <th className="pb-3 pt-2 pr-4 bg-black">Date programmée</th>
                <th className="pb-3 pt-2 bg-black">Actions</th>
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
                // Count failed results for this campaign
                const failedCount = campaign.results?.filter(r => r.status === 'failed').length || 0;
                const hasErrors = failedCount > 0 || campaignLogs.some(l => l.campaignId === campaign.id && l.type === 'error');
                const convType = activeConversations.find(ac => ac.conversation_id === campaign.targetConversationId)?.type;
                
                return (
                  <tr key={campaign.id} className="border-b border-purple-500/20 text-white text-sm">
                    <td className="py-3 pr-4">
                      <div className="flex items-center gap-2">
                        {hasErrors && (
                          <span className="w-2 h-2 bg-red-500 rounded-full flex-shrink-0" title="Erreur détectée"></span>
                        )}
                        <span className="font-medium">{campaign.name}</span>
                      </div>
                    </td>
                    <td className="py-3 pr-4">
                      <div className="flex items-center gap-1">
                        {campaign.channels?.internal ? (
                          <>
                            <span>{convType === 'group' ? '👥' : '👤'}</span>
                            <span className="truncate max-w-[150px]">{campaign.targetConversationName || 'Chat Interne'}</span>
                          </>
                        ) : campaign.targetType === "all" ? (
                          `Tous (${campaign.results?.length || 0})`
                        ) : (
                          campaign.selectedContacts?.length || 0
                        )}
                      </div>
                    </td>
                    <td className="py-3 pr-4">
                      {campaign.channels?.whatsapp && <span className="mr-1">📱</span>}
                      {campaign.channels?.email && <span className="mr-1">📧</span>}
                      {campaign.channels?.instagram && <span className="mr-1">📸</span>}
                      {campaign.channels?.group && <span className="mr-1">💬</span>}
                      {campaign.channels?.internal && <span className="text-green-400">💌</span>}
                    </td>
                    <td className="py-3 pr-4">
                      <div className="flex items-center gap-1">
                        {campaign.status === 'draft' && <span className="px-2 py-1 rounded text-xs bg-gray-600">📝 Brouillon</span>}
                        {campaign.status === 'scheduled' && <span className="px-2 py-1 rounded text-xs bg-yellow-600">📅 Programmé</span>}
                        {campaign.status === 'sending' && <span className="px-2 py-1 rounded text-xs bg-blue-600">🔄 En cours</span>}
                        {campaign.status === 'completed' && !hasErrors && <span className="px-2 py-1 rounded text-xs bg-green-600">✅ Envoyé</span>}
                        {campaign.status === 'completed' && hasErrors && (
                          <span className="px-2 py-1 rounded text-xs bg-orange-600" title={`${failedCount} échec(s)`}>
                            ⚠️ Partiel ({failedCount})
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 pr-4 text-xs opacity-70">
                      {campaign.scheduledAt ? new Date(campaign.scheduledAt).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : 'Immédiat'}
                    </td>
                    <td className="py-3">
                      <div className="flex gap-2">
                        {/* Bouton Modifier - Disponible pour TOUTES les campagnes */}
                        <button 
                          type="button"
                          onClick={() => handleEditCampaign(campaign)} 
                          className="px-3 py-1 rounded text-xs bg-yellow-600 hover:bg-yellow-700"
                          data-testid={`edit-campaign-${campaign.id}`}
                          title="Modifier la campagne"
                        >
                          ✏️
                        </button>
                        {/* Bouton Lancer - UNIQUEMENT pour draft (Brouillon) */}
                        {campaign.status === 'draft' && (
                          <button 
                            type="button"
                            onClick={(e) => launchCampaignWithSend(e, campaign.id)} 
                            className="px-3 py-1 rounded text-xs bg-purple-600 hover:bg-purple-700"
                            data-testid={`launch-campaign-${campaign.id}`}
                          >
                            🚀 Lancer
                          </button>
                        )}
                        {/* Badge Automatique - Pour les campagnes programmées */}
                        {campaign.status === 'scheduled' && (
                          <span 
                            className="px-3 py-1 rounded text-xs bg-yellow-600/30 text-yellow-400 border border-yellow-500/30"
                            title={`Envoi automatique le ${campaign.scheduledAt ? new Date(campaign.scheduledAt).toLocaleString('fr-FR') : 'bientôt'}`}
                          >
                            ⏳ Auto
                          </span>
                        )}
                        {/* Bouton Relancer - Pour les campagnes envoyées ou échouées */}
                        {(campaign.status === 'sent' || campaign.status === 'completed' || campaign.status === 'failed') && (
                          <button 
                            type="button"
                            onClick={(e) => launchCampaignWithSend(e, campaign.id)} 
                            className="px-3 py-1 rounded text-xs bg-green-600 hover:bg-green-700"
                            data-testid={`relaunch-campaign-${campaign.id}`}
                          >
                            🔄 Relancer
                          </button>
                        )}
                        {campaign.status === 'sending' && (
                          <button onClick={() => {/* setTab not available here */}} className="px-3 py-1 rounded text-xs bg-blue-600 hover:bg-blue-700">
                            👁️ Voir
                          </button>
                        )}
                        <button onClick={() => deleteCampaign(campaign.id)} className="px-3 py-1 rounded text-xs bg-red-600/30 hover:bg-red-600/50 text-red-400">
                          🗑️
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {campaigns.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-white opacity-50">
                    Aucune campagne créée pour le moment
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        
        {/* Expanded Campaign Details (when sending) */}
        {campaigns.filter(c => c.status === 'sending').map(campaign => {
          // Helper to check if WhatsApp link is valid
          const getWhatsAppLinkOrError = (result) => {
            if (result.channel !== 'whatsapp') return { link: null, error: false };
            const link = generateWhatsAppLink(result.contactPhone, campaign.message, campaign.mediaUrl, result.contactName);
            return { link, error: !link };
          };
          
          return (
            <div key={`detail-${campaign.id}`} className="mt-6 p-4 rounded-xl glass">
              <h4 className="text-white font-semibold mb-3">🔄 {campaign.name} - En cours d'envoi</h4>
              <p className="text-white text-sm mb-3 opacity-70">Cliquez sur un contact pour ouvrir le lien et marquer comme envoyé</p>
              
              <div className="space-y-2" style={{ maxHeight: '300px', overflowY: 'auto' }}>
                {campaign.results?.map((result, idx) => {
                  const whatsappResult = result.channel === 'whatsapp' ? getWhatsAppLinkOrError(result) : { link: null, error: false };
                  const hasError = (result.channel === 'whatsapp' && whatsappResult.error) || 
                                  (result.channel === 'email' && !result.contactEmail) ||
                                  result.status === 'failed';
                  
                  return (
                    <div key={idx} className={`flex items-center justify-between gap-2 p-2 rounded-lg ${hasError ? 'bg-red-900/30 border border-red-500/30' : 'bg-black/30'}`}>
                      <div className="flex items-center gap-2 flex-1 min-w-0">
                        {hasError && <span className="w-2 h-2 bg-red-500 rounded-full flex-shrink-0"></span>}
                        <span className="text-white text-sm truncate">{result.contactName}</span>
                        <span className="text-xs opacity-50">
                          {result.channel === 'whatsapp' && '📱'}
                          {result.channel === 'email' && '📧'}
                          {result.channel === 'instagram' && '📸'}
                        </span>
                        {result.channel === 'whatsapp' && (
                          <span className="text-xs opacity-40 truncate">({result.contactPhone || 'Pas de numéro'})</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        {result.status === 'pending' && !hasError && (
                          <a 
                            href={result.channel === 'whatsapp' 
                              ? whatsappResult.link
                              : result.channel === 'email'
                              ? generateEmailLink(result.contactEmail, campaign.name, campaign.message, campaign.mediaUrl, result.contactName)
                              : `https://instagram.com`}
                            target="_blank" rel="noopener noreferrer"
                            onClick={() => markResultSent(campaign.id, result.contactId, result.channel)}
                            className="px-3 py-1 rounded text-xs bg-purple-600 hover:bg-purple-700 text-white"
                          >
                            Envoyer
                          </a>
                        )}
                        {result.status === 'pending' && hasError && (
                          <span className="px-2 py-1 rounded text-xs bg-red-600/30 text-red-400">
                            {result.channel === 'whatsapp' ? '❌ N° invalide' : '❌ Email manquant'}
                          </span>
                        )}
                        {result.status === 'sent' && (
                          <div className="flex items-center gap-1">
                            <span className="px-2 py-1 rounded text-xs bg-green-600/30 text-green-400">✅ Envoyé</span>
                            {/* v11: Tracking delivery/read */}
                            {result.deliveredAt && (
                              <span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-600/30 text-blue-400" title={`Reçu: ${new Date(result.deliveredAt).toLocaleString('fr-FR')}`}>📬</span>
                            )}
                            {result.readAt && (
                              <span className="px-1.5 py-0.5 rounded text-[10px] bg-purple-600/30 text-purple-400" title={`Lu: ${new Date(result.readAt).toLocaleString('fr-FR')}`}>👁️</span>
                            )}
                          </div>
                        )}
                        {result.status === 'failed' && (
                          <span className="px-2 py-1 rounded text-xs bg-red-600/30 text-red-400" title={result.error || ''}>❌ Échec</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
              
              <div className="mt-3 flex justify-between text-xs">
                <span className="text-purple-400">
                  Progression: {campaign.results?.filter(r => r.status === 'sent').length || 0} / {campaign.results?.length || 0} envoyé(s)
                </span>
                {campaign.results?.some(r => r.status === 'pending' && (
                  (r.channel === 'whatsapp' && !formatPhoneForWhatsApp(r.contactPhone)) ||
                  (r.channel === 'email' && !r.contactEmail)
                )) && (
                  <span className="text-red-400">
                    ⚠️ Certains contacts ont des informations manquantes
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default memo(CampaignManager);

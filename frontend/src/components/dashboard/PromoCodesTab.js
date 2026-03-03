/**
 * PromoCodesTab Component v13.8
 * Section Codes Promo - VERSION COMPLÈTE RESTAURÉE
 * Inclut: Edition, Duplication, Durée validité, Max uses, Sélection contacts
 */
import React, { useRef } from 'react';
import { CreditsGate } from './index';

// Icônes
const FolderIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
  </svg>
);

const PromoCodesTab = ({
  // Credit check
  hasCreditsFor,
  servicePrices,
  coachCredits,
  setTab,
  // Search
  codesSearch,
  setCodesSearch,
  // Promo codes data
  discountCodes,
  newCode,
  setNewCode,
  // Batch mode
  isBatchMode,
  setIsBatchMode,
  batchLoading,
  // Manual contact
  showManualContactForm,
  setShowManualContactForm,
  manualContact,
  setManualContact,
  // Beneficiaries selection
  uniqueCustomers,
  selectedBeneficiaries,
  toggleBeneficiarySelection,
  // Articles/Courses selection
  courses,
  offers,
  toggleCourseSelection,
  removeAllowedArticle,
  // Actions
  addCode,
  deleteCode,
  toggleCode,
  duplicateCode,
  editCode,
  addManualContact,
  handleImportCSV,
  exportPromoCodesCSV,
  manualSanitize,
  // Translations
  t
}) => {
  const fileInputRef = useRef(null);

  // Helper pour formater les dates
  const formatDate = (dateVal) => {
    if (!dateVal) return '—';
    try {
      const d = new Date(dateVal);
      return isNaN(d.getTime()) ? '—' : d.toLocaleDateString('fr-CH');
    } catch { return '—'; }
  };

  return (
    <div className="card-gradient rounded-xl p-4 sm:p-6" data-testid="promo-codes-tab">
      {/* Vérification crédits */}
      {!hasCreditsFor('promo_code') ? (
        <CreditsGate 
          serviceName="codes"
          requiredCredits={servicePrices.promo_code}
          currentCredits={coachCredits}
          onGoToBoutique={() => setTab('boutique')}
          testId="credits-lock-codes"
        />
      ) : (
      <>
      {/* En-tête avec recherche */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-4 gap-3">
        <h2 className="font-semibold text-white text-lg sm:text-xl">{t('promoCodes')}</h2>
        <div className="relative w-full sm:w-64">
          <input
            type="text"
            placeholder="🔍 Rechercher un code..."
            value={codesSearch}
            onChange={(e) => setCodesSearch(e.target.value)}
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)', color: '#fff' }}
            data-testid="codes-search-input"
          />
          {codesSearch && (
            <button
              onClick={() => setCodesSearch('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-white/50 hover:text-white"
            >✕</button>
          )}
        </div>
      </div>
      
      {/* Boutons d'action */}
      <div className="flex justify-end mb-4 flex-wrap gap-2">
        <button 
          type="button"
          onClick={() => setShowManualContactForm(!showManualContactForm)} 
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-white text-xs sm:text-sm transition-all"
          style={{ 
            background: showManualContactForm ? 'rgba(239, 68, 68, 0.2)' : 'rgba(34, 197, 94, 0.2)',
            border: showManualContactForm ? '1px solid rgba(239, 68, 68, 0.4)' : '1px solid rgba(34, 197, 94, 0.4)'
          }}
          data-testid="add-manual-contact-btn"
        >
          {showManualContactForm ? '✕ Fermer' : t('addManualContact')}
        </button>
        <input type="file" accept=".csv" ref={fileInputRef} onChange={handleImportCSV} style={{ display: 'none' }} />
        <button onClick={() => fileInputRef.current?.click()} className="flex items-center gap-2 px-3 py-2 rounded-lg glass text-white text-xs sm:text-sm" data-testid="import-csv-btn">
          <FolderIcon /> {t('importCSV')}
        </button>
        <button 
          onClick={exportPromoCodesCSV} 
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-white text-xs sm:text-sm"
          style={{ background: 'rgba(139, 92, 246, 0.3)', border: '1px solid rgba(139, 92, 246, 0.5)' }}
          data-testid="export-csv-btn"
        >
          📥 {t('exportCSV')}
        </button>
      </div>
      
      {/* Manual Contact Form */}
      {showManualContactForm && (
        <form onSubmit={addManualContact} className="mb-6 p-4 rounded-lg border border-green-500/30" style={{ background: 'rgba(34, 197, 94, 0.1)' }}>
          <h3 className="text-white font-semibold mb-3 text-sm">👤 Ajouter un nouveau contact</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
            <input 
              type="text" 
              placeholder={t('manualContactName')} 
              value={manualContact.name} 
              onChange={e => setManualContact({ ...manualContact, name: e.target.value })}
              className="px-3 py-2 rounded-lg neon-input text-sm" 
              required
              data-testid="manual-contact-name"
            />
            <input 
              type="email" 
              placeholder={t('manualContactEmail')} 
              value={manualContact.email} 
              onChange={e => setManualContact({ ...manualContact, email: e.target.value })}
              className="px-3 py-2 rounded-lg neon-input text-sm" 
              required
              data-testid="manual-contact-email"
            />
            <input 
              type="tel" 
              placeholder={t('manualContactWhatsapp')} 
              value={manualContact.whatsapp} 
              onChange={e => setManualContact({ ...manualContact, whatsapp: e.target.value })}
              className="px-3 py-2 rounded-lg neon-input text-sm"
              data-testid="manual-contact-whatsapp"
            />
          </div>
          <button type="submit" className="px-4 py-2 rounded-lg text-sm font-medium text-white" style={{ background: 'rgba(34, 197, 94, 0.6)' }} data-testid="submit-manual-contact">
            ✓ Ajouter le contact
          </button>
        </form>
      )}
      
      {/* Formulaire de création de code - COMPLET */}
      <form onSubmit={addCode} className="mb-6 p-4 rounded-lg glass">
        {/* Toggle Mode Série */}
        <div className="flex items-center justify-between mb-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input 
              type="checkbox" 
              checked={isBatchMode} 
              onChange={(e) => setIsBatchMode(e.target.checked)}
              className="w-5 h-5 rounded accent-purple-500"
              data-testid="batch-mode-toggle"
            />
            <span className="text-white font-medium">{t('batchGeneration')}</span>
          </label>
          <div className="flex items-center gap-2">
            {isBatchMode && (
              <span className="text-xs text-purple-300 opacity-70">{t('batchMax')}</span>
            )}
            <button 
              type="button"
              onClick={manualSanitize}
              className="px-3 py-1 rounded-lg text-xs"
              style={{ background: 'rgba(251, 191, 36, 0.2)', color: '#fbbf24', border: '1px solid rgba(251, 191, 36, 0.4)' }}
              title="Nettoyer les données fantômes"
              data-testid="sanitize-btn"
            >
              🧹 Nettoyer
            </button>
          </div>
        </div>
        
        {/* Champs de génération en série */}
        {isBatchMode && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4 p-3 rounded-lg" style={{ background: 'rgba(139, 92, 246, 0.15)', border: '1px solid rgba(139, 92, 246, 0.3)' }}>
            <div>
              <label className="block text-white text-xs mb-1 opacity-70">{t('codePrefix')}</label>
              <input 
                type="text" 
                placeholder="VIP, PROMO..." 
                value={newCode.prefix} 
                onChange={e => setNewCode({ ...newCode, prefix: e.target.value.toUpperCase() })}
                className="w-full px-3 py-2 rounded-lg neon-input text-sm uppercase" 
                data-testid="batch-prefix"
                maxLength={15}
              />
            </div>
            <div>
              <label className="block text-white text-xs mb-1 opacity-70">{t('batchCount')}</label>
              <input 
                type="number" 
                min="1" 
                max="20" 
                placeholder="1-20" 
                value={newCode.batchCount} 
                onChange={e => setNewCode({ ...newCode, batchCount: Math.min(20, Math.max(1, parseInt(e.target.value) || 1)) })}
                className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
                data-testid="batch-count"
              />
            </div>
          </div>
        )}
        
        {/* Champ code unique */}
        {!isBatchMode && (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <input type="text" placeholder={t('codePromo')} value={newCode.code} onChange={e => setNewCode({ ...newCode, code: e.target.value })}
              className="px-3 py-2 rounded-lg neon-input text-sm" data-testid="new-code-name" />
            <select value={newCode.type} onChange={e => setNewCode({ ...newCode, type: e.target.value })} className="px-3 py-2 rounded-lg neon-input text-sm" data-testid="new-code-type">
              <option value="">{t('type')}</option>
              <option value="100%">100% (Gratuit)</option>
              <option value="%">%</option>
              <option value="CHF">CHF</option>
            </select>
            <input type="number" placeholder={t('value')} value={newCode.value} onChange={e => setNewCode({ ...newCode, value: e.target.value })}
              className="px-3 py-2 rounded-lg neon-input text-sm" data-testid="new-code-value" />
          </div>
        )}
        
        {/* Type et valeur pour mode série */}
        {isBatchMode && (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 mb-4">
            <select value={newCode.type} onChange={e => setNewCode({ ...newCode, type: e.target.value })} className="px-3 py-2 rounded-lg neon-input text-sm" data-testid="batch-code-type">
              <option value="">{t('type')}</option>
              <option value="100%">100% (Gratuit)</option>
              <option value="%">%</option>
              <option value="CHF">CHF</option>
            </select>
            <input type="number" placeholder={t('value')} value={newCode.value} onChange={e => setNewCode({ ...newCode, value: e.target.value })}
              className="px-3 py-2 rounded-lg neon-input text-sm" data-testid="batch-code-value" />
          </div>
        )}
        
        {/* ============ SÉLECTION MULTIPLE DES BÉNÉFICIAIRES ============ */}
        <div className="mb-4">
          <label className="block text-white text-xs mb-2 opacity-70">
            👥 Sélectionner les bénéficiaires ({selectedBeneficiaries?.length || 0} sélectionné{(selectedBeneficiaries?.length || 0) > 1 ? 's' : ''})
          </label>
          <div className="border border-purple-500/30 rounded-lg p-3 bg-purple-900/10" style={{ maxHeight: '120px', overflowY: 'auto' }}>
            <div className="flex flex-wrap gap-2">
              {uniqueCustomers && uniqueCustomers.length > 0 ? uniqueCustomers.map((c, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => toggleBeneficiarySelection && toggleBeneficiarySelection(c.email)}
                  className={`px-2 py-1 rounded text-xs transition-all flex items-center gap-1 ${
                    selectedBeneficiaries?.includes(c.email) 
                      ? 'bg-pink-600 text-white' 
                      : 'bg-gray-700 text-white hover:bg-gray-600'
                  }`}
                  data-testid={`beneficiary-${i}`}
                >
                  {selectedBeneficiaries?.includes(c.email) && <span>✓</span>}
                  {c.name ? c.name.split(' ')[0] : 'Contact'}
                </button>
              )) : (
                <span className="text-white text-xs opacity-50">Aucun contact disponible</span>
              )}
            </div>
          </div>
          {/* Affichage des bénéficiaires sélectionnés */}
          {selectedBeneficiaries && selectedBeneficiaries.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {selectedBeneficiaries.map((email, i) => {
                const customer = uniqueCustomers?.find(c => c.email === email);
                return (
                  <span key={i} className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-pink-600/30 text-pink-300">
                    {customer?.name || email}
                    <button
                      type="button"
                      onClick={() => toggleBeneficiarySelection && toggleBeneficiarySelection(email)}
                      className="hover:text-white ml-1"
                    >×</button>
                  </span>
                );
              })}
            </div>
          )}
        </div>
        
        {/* ============ PARAMÈTRES AVANCÉS ============ */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          {/* Nombre max d'utilisations */}
          <div>
            <label className="block text-white text-xs mb-1 opacity-70">{t('maxUses')} (limite)</label>
            <input 
              type="number" 
              placeholder="∞ = illimité" 
              value={newCode.maxUses || ''} 
              onChange={e => setNewCode({ ...newCode, maxUses: e.target.value })}
              className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
              data-testid="max-uses-input"
            />
          </div>
          
          {/* Date d'expiration */}
          <div>
            <label className="block text-white text-xs mb-1 opacity-70">📅 Date d'expiration</label>
            <input 
              type="date" 
              value={newCode.expiresAt || ''} 
              onChange={e => setNewCode({ ...newCode, expiresAt: e.target.value })}
              className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
              data-testid="expires-at-input"
            />
          </div>
          
          {/* Articles autorisés */}
          <div>
            <label className="block text-white text-xs mb-1 opacity-70">📦 Articles autorisés</label>
            <div className="courses-scroll-container" style={{ maxHeight: '120px', overflowY: 'auto', padding: '4px' }} data-testid="articles-scroll-container">
              {/* Section Cours */}
              {courses && courses.length > 0 && (
                <div className="mb-2">
                  <p className="text-white text-xs opacity-40 mb-1">📅 Cours</p>
                  <div className="flex flex-wrap gap-1">
                    {courses.map(c => (
                      <button key={c.id} type="button" onClick={() => toggleCourseSelection && toggleCourseSelection(c.id)}
                        className={`px-2 py-1 rounded text-xs transition-all ${newCode.courses?.includes(c.id) ? 'bg-purple-600' : 'bg-gray-700 hover:bg-gray-600'}`}
                        style={{ color: 'white' }} data-testid={`course-select-${c.id}`}>{c.name ? c.name.split(' – ')[0] : 'Cours'}</button>
                    ))}
                  </div>
                </div>
              )}
              {/* Section Offres */}
              {offers && offers.length > 0 && (
                <div className="mt-2">
                  <p className="text-white text-xs opacity-40 mb-1">🎫 Offres</p>
                  <div className="flex flex-wrap gap-1">
                    {offers.map(o => (
                      <button key={o.id} type="button" onClick={() => toggleCourseSelection && toggleCourseSelection(o.id)}
                        className={`px-2 py-1 rounded text-xs transition-all ${newCode.courses?.includes(o.id) ? 'bg-blue-600' : 'bg-gray-700 hover:bg-gray-600'}`}
                        style={{ color: 'white' }} data-testid={`offer-select-${o.id}`}>{o.name}</button>
                    ))}
                  </div>
                </div>
              )}
              {(!courses || courses.length === 0) && (!offers || offers.length === 0) && (
                <span className="text-white text-xs opacity-50">Tous les articles</span>
              )}
            </div>
            {/* Articles sélectionnés */}
            {newCode.courses && newCode.courses.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {newCode.courses.map(articleId => {
                  const course = courses?.find(c => c.id === articleId);
                  const offer = offers?.find(o => o.id === articleId);
                  const name = course?.name?.split(' – ')[0] || offer?.name || articleId;
                  return (
                    <span key={articleId} className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-purple-600/30 text-purple-300">
                      {name}
                      <button type="button" onClick={() => removeAllowedArticle && removeAllowedArticle(articleId)} className="hover:text-white ml-1">×</button>
                    </span>
                  );
                })}
              </div>
            )}
          </div>
        </div>
        
        <button 
          type="submit" 
          className="btn-primary px-6 py-2 rounded-lg text-sm flex items-center gap-2" 
          data-testid={isBatchMode ? "generate-batch" : "add-code"}
          disabled={batchLoading}
        >
          {batchLoading ? (
            <><span className="animate-spin">⏳</span> Création en cours...</>
          ) : isBatchMode ? (
            <>{t('generateBatch')} ({newCode.batchCount || 1} codes)</>
          ) : (
            t('add')
          )}
        </button>
      </form>
      
      {/* ============ LISTE DES CODES ============ */}
      <div className="space-y-3" style={{ maxHeight: '400px', overflowY: 'auto' }}>
        {(codesSearch ? discountCodes.filter(c => 
          c.code?.toLowerCase().includes(codesSearch.toLowerCase()) ||
          c.assignedEmails?.some(e => e.toLowerCase().includes(codesSearch.toLowerCase()))
        ) : discountCodes).map(code => (
          <div 
            key={code.id} 
            className={`glass rounded-lg p-4 ${!code.active ? 'opacity-50' : ''}`}
            data-testid={`promo-code-${code.id}`}
          >
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
              <div className="flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-white font-bold text-lg">{code.code}</span>
                  <span className="px-2 py-0.5 rounded text-xs" style={{ background: 'rgba(217, 28, 210, 0.3)', color: '#D91CD2' }}>
                    {code.type === '100%' ? 'GRATUIT' : `${code.value}${code.type}`}
                  </span>
                  {code.linkedOfferName && (
                    <span className="px-2 py-0.5 rounded text-xs" style={{ background: 'rgba(139, 92, 246, 0.3)', color: '#a78bfa' }}>
                      🎁 {code.linkedOfferName}
                    </span>
                  )}
                </div>
                {/* Bénéficiaires */}
                {code.assignedEmails?.length > 0 && (
                  <p className="text-white/50 text-xs mt-1">
                    👤 {code.assignedEmails.slice(0, 3).join(', ')}{code.assignedEmails.length > 3 ? ` +${code.assignedEmails.length - 3}` : ''}
                  </p>
                )}
                {/* Stats utilisation */}
                <p className="text-white/30 text-xs mt-1">
                  Utilisé: {code.usedCount || code.used || 0}/{code.maxUses || '∞'}
                  {code.expiresAt && ` • Expire: ${formatDate(code.expiresAt)}`}
                </p>
              </div>
              
              {/* BOUTONS D'ACTION */}
              <div className="flex items-center gap-2 flex-wrap">
                {/* Toggle Actif/Inactif */}
                <button
                  onClick={() => toggleCode && toggleCode(code)}
                  className={`px-3 py-1.5 rounded text-xs font-medium ${code.active ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}
                  data-testid={`toggle-code-${code.id}`}
                >
                  {code.active ? '✓ Actif' : '✗ Inactif'}
                </button>
                
                {/* Bouton Éditer */}
                {editCode && (
                  <button
                    onClick={() => editCode(code)}
                    className="px-3 py-1.5 rounded text-xs bg-blue-500/20 text-blue-400 hover:bg-blue-500/40"
                    data-testid={`edit-code-${code.id}`}
                  >
                    ✏️ Éditer
                  </button>
                )}
                
                {/* Bouton Dupliquer */}
                {duplicateCode && (
                  <button
                    onClick={() => duplicateCode(code)}
                    className="px-3 py-1.5 rounded text-xs bg-purple-500/20 text-purple-400 hover:bg-purple-500/40"
                    data-testid={`duplicate-code-${code.id}`}
                  >
                    📋 Dupliquer
                  </button>
                )}
                
                {/* Bouton Supprimer */}
                <button
                  onClick={() => deleteCode && deleteCode(code.id)}
                  className="px-3 py-1.5 rounded text-xs bg-red-500/20 text-red-400 hover:bg-red-500/40"
                  data-testid={`delete-code-${code.id}`}
                >
                  🗑️
                </button>
              </div>
            </div>
          </div>
        ))}
        {(codesSearch ? discountCodes.filter(c => 
          c.code?.toLowerCase().includes(codesSearch.toLowerCase())
        ) : discountCodes).length === 0 && (
          <p className="text-center py-8 text-white opacity-50">
            {codesSearch ? 'Aucun code trouvé' : t('noPromoCode')}
          </p>
        )}
      </div>
      </>
      )}
    </div>
  );
};

export default PromoCodesTab;

/**
 * PromoCodesTab Component v14.0
 * Section Codes Promo - VERSION COMPLÈTE RESTAURÉE
 * Inclut: Edition, Duplication, Durée validité, Max uses, Sélection contacts
 * v14.0: Ajout bouton "Copier" le code
 */
import React, { useRef, useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { CreditsGate } from './index';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

// Icônes
const FolderIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
  </svg>
);

// v14.0: Icône Copier
const CopyIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
  </svg>
);

// v14.0: Icône Check (copié)
const CheckIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
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
  // v104: Edit mode
  editingCode,
  // Translations
  t
}) => {
  const fileInputRef = useRef(null);
  const [copiedCodeId, setCopiedCodeId] = useState(null); // v14.0: État pour bouton "Copié"
  // V185 F2: Feedback pour le bouton "Lien d'accès rapide"
  const [copiedSpaceLinkId, setCopiedSpaceLinkId] = useState(null);
  // V193: filtre dédié pour la grille des bénéficiaires (chips)
  const [beneficiariesFilter, setBeneficiariesFilter] = useState('');

  // V154: Category targeting for promo codes
  var [promoCategories, setPromoCategories] = useState([]);
  var [selectedTargetCategories, setSelectedTargetCategories] = useState([]);

  // v95: Charger les subscriptions par code pour afficher séances restantes
  const [codeSubscriptions, setCodeSubscriptions] = useState({});
  useEffect(() => {
    const loadSubscriptions = async () => {
      const subsMap = {};
      for (const code of discountCodes) {
        try {
          const res = await axios.get(`${API}/discount-codes/subscriptions/status`, {
            params: { code: code.code }
          });
          if (res.data?.subscriptions?.length > 0) {
            subsMap[code.code] = res.data.subscriptions;
          }
        } catch (err) { /* ignore */ }
      }
      setCodeSubscriptions(subsMap);
    };
    if (discountCodes?.length > 0) loadSubscriptions();
  }, [discountCodes]);

  // V154: Load categories for targeting
  useEffect(function() {
    axios.get(API + '/contact-categories', {
      headers: { 'X-User-Email': '' }
    }).then(function(res) {
      if (res.data.success) {
        setPromoCategories(res.data.categories || []);
      }
    }).catch(function() {});
  }, []);

  // v14.0: Fonction pour copier le code dans le presse-papier
  const copyCodeToClipboard = async (code) => {
    try {
      await navigator.clipboard.writeText(code.code);
      setCopiedCodeId(code.id);
      setTimeout(() => setCopiedCodeId(null), 2000); // Reset après 2 secondes
    } catch (err) {
      console.error('Erreur copie:', err);
      // Fallback pour navigateurs anciens
      const textArea = document.createElement('textarea');
      textArea.value = code.code;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopiedCodeId(code.id);
      setTimeout(() => setCopiedCodeId(null), 2000);
    }
  };

  // V185 F2: Copier le lien d'accès rapide /espace/{code}
  const copySpaceLinkToClipboard = async (code) => {
    const url = `${window.location.origin}/espace/${code.code}`;
    try {
      await navigator.clipboard.writeText(url);
    } catch (err) {
      const ta = document.createElement('textarea');
      ta.value = url;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    setCopiedSpaceLinkId(code.id);
    setTimeout(() => setCopiedSpaceLinkId(null), 2000);
  };

  // V192: Recherche multi-critères corrigée (code, nom, email, téléphone/WhatsApp)
  // Bugs fixés depuis v150 : .find→.some (multi-match), phone normalisé en
  // chiffres, fallback nom/email sur les champs directs du code, code mort
  // customerEmailsByNameOrPhone supprimé.
  const filteredDiscountCodes = useMemo(() => {
    if (!codesSearch) return discountCodes;
    const q = codesSearch.toLowerCase().trim();
    if (!q) return discountCodes;
    const qDigits = q.replace(/\D/g, ''); // chiffres uniquement pour matcher des numéros formatés

    const matchesText = (v) => !!v && String(v).toLowerCase().includes(q);
    const matchesPhone = (v) => {
      if (!qDigits) return false;
      const d = String(v || '').replace(/\D/g, '');
      return d.length > 0 && d.includes(qDigits);
    };

    return discountCodes.filter(c => {
      // 1. Code lui-même
      if (matchesText(c.code)) return true;

      // 2. Champs bénéficiaire directement sur le code
      if (matchesText(c.name)) return true;
      if (matchesText(c.assignedName)) return true;
      if (matchesText(c.beneficiaryName)) return true;
      if (matchesText(c.assignedEmail)) return true;
      if (Array.isArray(c.assignedEmails) && c.assignedEmails.some(e => matchesText(e))) return true;
      if (matchesText(c.assignedPhone) || matchesText(c.whatsapp)) return true;
      if (matchesPhone(c.assignedPhone) || matchesPhone(c.whatsapp)) return true;

      // 3. Abonnés ayant utilisé ce code (subscriptions)
      const subs = codeSubscriptions[c.code];
      if (Array.isArray(subs) && subs.some(sub =>
        matchesText(sub.name) ||
        matchesText(sub.email) ||
        matchesText(sub.whatsapp) ||
        matchesText(sub.phone) ||
        matchesPhone(sub.whatsapp) ||
        matchesPhone(sub.phone)
      )) return true;

      // 4. Cross-référence : un contact (uniqueCustomers) dont l'email est
      // assigné à ce code peut matcher via son nom/email/téléphone
      if (Array.isArray(uniqueCustomers) && uniqueCustomers.length > 0) {
        const assignedEmails = new Set(
          [
            ...(c.assignedEmails || []),
            ...(c.assignedEmail ? [c.assignedEmail] : []),
          ].map(e => (e || '').toLowerCase())
        );
        // Si aucune assignation, on n'a rien à cross-référencer
        if (assignedEmails.size > 0) {
          const someMatch = uniqueCustomers.some(cust => {
            const custMatches = matchesText(cust.name) || matchesText(cust.email)
              || matchesPhone(cust.phone) || matchesPhone(cust.whatsapp);
            if (!custMatches) return false;
            return assignedEmails.has((cust.email || '').toLowerCase());
          });
          if (someMatch) return true;
        }
      }

      return false;
    });
  }, [codesSearch, discountCodes, codeSubscriptions, uniqueCustomers]);

  // V193: Filtre dédié pour les chips bénéficiaires (recherche nom / email / téléphone)
  const filteredBeneficiaries = useMemo(() => {
    if (!Array.isArray(uniqueCustomers)) return [];
    const q = (beneficiariesFilter || '').toLowerCase().trim();
    if (!q) return uniqueCustomers;
    const qDigits = q.replace(/\D/g, '');
    const matchesText = (v) => !!v && String(v).toLowerCase().includes(q);
    const matchesPhone = (v) => {
      if (!qDigits) return false;
      const d = String(v || '').replace(/\D/g, '');
      return d.length > 0 && d.includes(qDigits);
    };
    return uniqueCustomers.filter(c =>
      matchesText(c.name) ||
      matchesText(c.email) ||
      matchesText(c.phone) ||
      matchesText(c.whatsapp) ||
      matchesPhone(c.phone) ||
      matchesPhone(c.whatsapp)
    );
  }, [uniqueCustomers, beneficiariesFilter]);

  // v104: Auto-remplir maxUses quand un article est sélectionné
  const resolvedSessionsFromOffer = useMemo(() => {
    if (!newCode.courses?.length) return null;
    const allArticles = [...(courses || []), ...(offers || [])];
    for (const articleId of newCode.courses) {
      const article = allArticles.find(a => a.id === articleId);
      if (article?.name) {
        const match = article.name.match(/[x×]\s*(\d+)/i);
        if (match) return { count: parseInt(match[1]), name: article.name };
        if (/unit|à l'unité|unique/i.test(article.name)) return { count: 1, name: article.name };
      }
    }
    return null;
  }, [newCode.courses, courses, offers]);

  // Auto-populate maxUses when article changes (only if maxUses is empty)
  useEffect(() => {
    if (resolvedSessionsFromOffer && !newCode.maxUses) {
      setNewCode(prev => ({ ...prev, maxUses: String(resolvedSessionsFromOffer.count) }));
    }
  }, [resolvedSessionsFromOffer]); // eslint-disable-line react-hooks/exhaustive-deps

  // Helper pour formater les dates
  const formatDate = (dateVal) => {
    if (!dateVal) return '—';
    try {
      const d = new Date(dateVal);
      return isNaN(d.getTime()) ? '—' : d.toLocaleDateString('fr-CH');
    } catch { return '—'; }
  };

  // V154: Reset selectedTargetCategories when form is cleared or editing is cancelled
  useEffect(function() {
    // Reset when not editing
    if (!editingCode) {
      setSelectedTargetCategories([]);
    }
  }, [editingCode]);

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
            placeholder="🔍 Rechercher par code, nom, email, WhatsApp..."
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
      
      {!codesSearch && (<>
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
      <form onSubmit={function(e) {
        // V154: Add targetCategories to form submission
        setNewCode(function(prev) {
          return { ...prev, targetCategories: selectedTargetCategories };
        });
        // Call the original addCode handler
        addCode(e);
      }} className="mb-6 p-4 rounded-lg glass">
        {/* v104: Bandeau mode édition avec email bénéficiaire */}
        {editingCode && (
          <div className="mb-4 p-3 rounded-lg flex items-center gap-3 flex-wrap" style={{ background: 'rgba(59, 130, 246, 0.1)', border: '1px solid rgba(59, 130, 246, 0.3)' }}>
            <span className="text-blue-400 text-sm font-bold">✏️ Mode Édition</span>
            <span className="text-white/60 text-xs">Code: <span className="text-white font-mono">{newCode.code}</span></span>
            {(newCode.assignedEmails?.length > 0 || selectedBeneficiaries?.length > 0) && (
              <span className="text-xs px-2 py-1 rounded-full" style={{ background: 'rgba(217, 28, 210, 0.15)', color: '#D91CD2', border: '1px solid rgba(217, 28, 210, 0.3)' }}>
                📧 Bénéficiaire: {(selectedBeneficiaries?.length > 0 ? selectedBeneficiaries : newCode.assignedEmails)?.join(', ')}
              </span>
            )}
          </div>
        )}
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
          {/* V193: Filtre dédié pour les chips bénéficiaires */}
          <div className="relative mb-2">
            <input
              type="text"
              placeholder="🔍 Filtrer les bénéficiaires..."
              value={beneficiariesFilter}
              onChange={(e) => setBeneficiariesFilter(e.target.value)}
              className="w-full px-3 py-2 rounded-lg neon-input text-xs"
              data-testid="beneficiaries-filter-input"
            />
            {beneficiariesFilter && (
              <button
                type="button"
                onClick={() => setBeneficiariesFilter('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-white/40 hover:text-white text-xs"
                aria-label="Effacer le filtre"
              >
                ✕
              </button>
            )}
          </div>
          <div className="border border-purple-500/30 rounded-lg p-3 bg-purple-900/10" style={{ maxHeight: '160px', overflowY: 'auto' }}>
            <div className="flex flex-wrap gap-2">
              {filteredBeneficiaries.length > 0 ? filteredBeneficiaries.map((c, i) => (
                <button
                  key={c.email || i}
                  type="button"
                  onClick={() => toggleBeneficiarySelection && toggleBeneficiarySelection(c.email)}
                  className={`px-2 py-1 rounded text-xs transition-all flex items-center gap-1 ${
                    selectedBeneficiaries?.includes(c.email)
                      ? 'bg-pink-600 text-white'
                      : 'bg-gray-700 text-white hover:bg-gray-600'
                  }`}
                  data-testid={`beneficiary-${i}`}
                  title={c.email + (c.whatsapp ? ' · ' + c.whatsapp : '')}
                >
                  {selectedBeneficiaries?.includes(c.email) && <span>✓</span>}
                  {c.name ? c.name.split(' ')[0] : 'Contact'}
                </button>
              )) : (
                <span className="text-white text-xs opacity-50">
                  {beneficiariesFilter
                    ? `Aucun bénéficiaire ne correspond à "${beneficiariesFilter}"`
                    : 'Aucun contact disponible'}
                </span>
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
          {/* Nombre max d'utilisations — v104: auto-rempli par l'article */}
          <div>
            <label className="block text-white text-xs mb-1 opacity-70">{t('maxUses')} (séances)</label>
            <input
              type="number"
              placeholder="1 par défaut"
              value={newCode.maxUses || ''}
              onChange={e => setNewCode({ ...newCode, maxUses: e.target.value })}
              className="w-full px-3 py-2 rounded-lg neon-input text-sm"
              data-testid="max-uses-input"
            />
            {resolvedSessionsFromOffer && (
              <p className="text-xs mt-1" style={{ color: '#a78bfa' }}>
                Auto-détecté : {resolvedSessionsFromOffer.count} séance(s) — {resolvedSessionsFromOffer.name}
              </p>
            )}
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

        {/* V154: Ciblage par catégories */}
        {promoCategories.length > 0 && (
          <div style={{ marginTop: '12px', marginBottom: '12px' }}>
            <label style={{ color: 'rgba(255,255,255,0.6)', fontSize: '11px', fontWeight: 500, display: 'block', marginBottom: '6px' }}>
              🎯 Ciblage par catégorie (optionnel)
            </label>
            <div style={{ display: 'flex', gap: '5px', flexWrap: 'wrap' }}>
              {promoCategories.map(function(cat) {
                var isActive = selectedTargetCategories.indexOf(cat.id) !== -1;
                return (
                  <button key={cat.id} type="button" onClick={function() {
                    setSelectedTargetCategories(function(prev) {
                      return isActive ? prev.filter(function(id) { return id !== cat.id; }) : prev.concat([cat.id]);
                    });
                  }} style={{
                    padding: '4px 10px', borderRadius: '12px', fontSize: '11px', fontWeight: 500, cursor: 'pointer',
                    background: isActive ? cat.color + '30' : 'rgba(255,255,255,0.04)',
                    border: '1px solid ' + (isActive ? cat.color + '66' : 'rgba(255,255,255,0.08)'),
                    color: isActive ? cat.color : 'rgba(255,255,255,0.4)'
                  }}>
                    {cat.icon} {cat.name}
                  </button>
                );
              })}
            </div>
            {selectedTargetCategories.length > 0 && (
              <p style={{ fontSize: '10px', color: 'rgba(255,255,255,0.4)', margin: '4px 0 0 0' }}>
                Ce code sera réservé aux contacts de ces catégories
              </p>
            )}
          </div>
        )}

        <button
          type="submit"
          className="btn-primary px-6 py-2 rounded-lg text-sm flex items-center gap-2"
          data-testid={isBatchMode ? "generate-batch" : "add-code"}
          disabled={batchLoading}
          style={editingCode ? { background: 'linear-gradient(135deg, #3b82f6, #2563eb)' } : {}}
        >
          {batchLoading ? (
            <><span className="animate-spin">⏳</span> Création en cours...</>
          ) : editingCode ? (
            '✏️ Mettre à jour le code'
          ) : isBatchMode ? (
            <>{t('generateBatch')} ({newCode.batchCount || 1} codes)</>
          ) : (
            t('add')
          )}
        </button>
      </form>
      </>)}
      
      {/* ============ LISTE DES CODES ============ */}
      <div className="space-y-3" style={{ maxHeight: codesSearch ? '80vh' : '400px', overflowY: 'auto' }}>
        {filteredDiscountCodes.map(code => (
          <div 
            key={code.id} 
            className={`glass rounded-lg p-4 ${!code.active ? 'opacity-50' : ''}`}
            data-testid={`promo-code-${code.id}`}
          >
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
              <div className="flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-white font-bold text-lg">{code.code}</span>
                  {/* v14.0: Bouton Copier le code */}
                  <button
                    onClick={() => copyCodeToClipboard(code)}
                    className={`p-1.5 rounded transition-all ${
                      copiedCodeId === code.id 
                        ? 'bg-green-500/30 text-green-400' 
                        : 'bg-white/10 text-white/60 hover:bg-white/20 hover:text-white'
                    }`}
                    title={copiedCodeId === code.id ? "Copié !" : "Copier le code"}
                    data-testid={`copy-code-${code.id}`}
                  >
                    {copiedCodeId === code.id ? <CheckIcon /> : <CopyIcon />}
                  </button>
                  <span className="px-2 py-0.5 rounded text-xs" style={{ background: 'rgba(217, 28, 210, 0.3)', color: '#D91CD2' }}>
                    {code.type === '100%' ? 'GRATUIT' : `${code.value}${code.type}`}
                  </span>
                  {code.linkedOfferName && (
                    <span className="px-2 py-0.5 rounded text-xs" style={{ background: 'rgba(139, 92, 246, 0.3)', color: '#a78bfa' }}>
                      🎁 {code.linkedOfferName}
                    </span>
                  )}
                </div>
                {/* Bénéficiaires — v106.1: support assignedEmail (string) + assignedEmails (array) */}
                {(code.assignedEmails?.length > 0 || code.assignedEmail) && (
                  <p className="text-white/50 text-xs mt-1">
                    📧 {(() => {
                      const emails = code.assignedEmails?.length > 0
                        ? code.assignedEmails
                        : code.assignedEmail ? [code.assignedEmail] : [];
                      return emails.slice(0, 3).join(', ') + (emails.length > 3 ? ` +${emails.length - 3}` : '');
                    })()}
                  </p>
                )}
                {/* Stats utilisation */}
                <p className="text-white/30 text-xs mt-1">
                  Utilisé: {code.usedCount || code.used || 0}/{code.maxUses || '∞'}
                  {code.expiresAt && ` • Expire: ${formatDate(code.expiresAt)}`}
                </p>
                {/* V194: Séances par abonné — dédupe par email et utilise code.maxUses
                    comme dénominateur (source de vérité) au lieu du total_sessions
                    figé de la subscription (qui peut être obsolète) */}
                {codeSubscriptions[code.code]?.length > 0 && (() => {
                  const seenEmails = new Set();
                  const uniqueSubs = codeSubscriptions[code.code].filter(sub => {
                    const key = (sub.email || sub.id || '').toLowerCase();
                    if (!key || seenEmails.has(key)) return false;
                    seenEmails.add(key);
                    return true;
                  });
                  const liveMax = Number(code.maxUses) > 0 ? Number(code.maxUses) : null;
                  return (
                    <div className="mt-2 space-y-1">
                      {uniqueSubs.map(sub => {
                        // Préférer code.maxUses (à jour) à sub.total_sessions (peut être obsolète)
                        const denom = liveMax != null ? liveMax : sub.total_sessions;
                        const used = Number(sub.used_sessions) || 0;
                        const remaining = denom != null ? Math.max(0, denom - used) : sub.remaining_sessions;
                        const showInfinite = sub.remaining_sessions === -1;
                        return (
                          <div key={sub.id || sub.email} className="flex items-center gap-2 text-xs">
                            <span className="text-purple-400">👤</span>
                            <span className="text-white/60">{sub.name || sub.email}</span>
                            <span className="px-1.5 py-0.5 rounded text-[10px]" style={{
                              background: remaining <= 0
                                ? 'rgba(239,68,68,0.2)'
                                : remaining <= 2
                                  ? 'rgba(245,158,11,0.2)'
                                  : 'rgba(34,197,94,0.2)',
                              color: remaining <= 0
                                ? '#ef4444'
                                : remaining <= 2
                                  ? '#f59e0b'
                                  : '#22c55e'
                            }}>
                              {showInfinite ? '∞' : `${used}/${denom != null ? denom : '?'}`} séances
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  );
                })()}
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
                
                {/* V185 F2: Bouton Lien d'accès rapide (uniquement codes actifs) */}
                {code.active && (
                  <button
                    onClick={() => copySpaceLinkToClipboard(code)}
                    className={`px-3 py-1.5 rounded text-xs font-medium ${copiedSpaceLinkId === code.id ? 'bg-green-500/20 text-green-400' : 'bg-pink-500/20 text-pink-400 hover:bg-pink-500/40'}`}
                    title={copiedSpaceLinkId === code.id ? 'Lien copié !' : `Copier ${window.location.origin}/espace/${code.code}`}
                    data-testid={`share-space-link-${code.id}`}
                  >
                    {copiedSpaceLinkId === code.id ? '✓ Copié' : '🔗 Lien'}
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
        {filteredDiscountCodes.length === 0 && (
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

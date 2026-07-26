/**
 * SubscriberForm.js - Formulaire d'identification abonné
 *
 * Extrait de ChatWidget.js pour alléger le fichier principal.
 * Gère:
 * - La saisie des 4 champs (Nom, WhatsApp, Email, Code Promo)
 * - L'affichage des erreurs de validation
 * - L'état de chargement pendant la validation
 * - Sauvegarde automatique des identifiants (localStorage)
 *   → Clé: afroboost_subscriber_info
 *   → Stocke UNIQUEMENT: name, whatsapp, email (JAMAIS le code promo)
 */

import React, { memo, useState, useEffect, useCallback } from 'react';

const STORAGE_KEY = 'afroboost_subscriber_info';
const PROFILE_KEY = 'afroboost_profile';
const IDENTITY_KEY = 'afroboost_identity'; // V218: identité posée par handleSmartEntry (tunnel/onboarding)

/**
 * Teste si localStorage est réellement disponible et persistant
 * @returns {boolean}
 */
const isLocalStorageAvailable = () => {
  try {
    const testKey = '__afroboost_ls_test__';
    localStorage.setItem(testKey, 'ok');
    const result = localStorage.getItem(testKey);
    localStorage.removeItem(testKey);
    return result === 'ok';
  } catch {
    return false;
  }
};

/**
 * Charge les données sauvegardées depuis localStorage
 * Vérifie d'abord afroboost_subscriber_info, puis fallback sur afroboost_profile
 * @returns {object|null} {name, whatsapp, email} ou null
 */
const loadSavedInfo = () => {
  try {
    // Source 1 : Données du formulaire abonné
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') {
        const name = (parsed.name || '').trim();
        const whatsapp = (parsed.whatsapp || '').trim();
        const email = (parsed.email || '').trim();
        // Au moins un champ non-vide
        if (name || whatsapp || email) {
          return { name, whatsapp, email };
        }
      }
    }
    // Source 2 (fallback) : Profil abonné validé précédemment
    const profileRaw = localStorage.getItem(PROFILE_KEY);
    if (profileRaw) {
      const profile = JSON.parse(profileRaw);
      if (profile && typeof profile === 'object') {
        const name = (profile.name || '').trim();
        const whatsapp = (profile.whatsapp || '').trim();
        const email = (profile.email || '').trim();
        if (name || whatsapp || email) {
          return { name, whatsapp, email };
        }
      }
    }
    // V218 Source 3 (fallback) : identité posée par le tunnel/onboarding (handleSmartEntry)
    // Utilise firstName → name pour ne pas redemander les infos déjà collectées
    const identityRaw = localStorage.getItem(IDENTITY_KEY);
    if (identityRaw) {
      const identity = JSON.parse(identityRaw);
      if (identity && typeof identity === 'object') {
        const name = (identity.firstName || identity.name || '').trim();
        const whatsapp = (identity.whatsapp || '').trim();
        const email = (identity.email || '').trim();
        if (name || whatsapp || email) {
          return { name, whatsapp, email };
        }
      }
    }
    return null;
  } catch {
    return null;
  }
};

/**
 * Sauvegarde les infos dans localStorage avec vérification
 * Ne sauvegarde PAS si tous les champs sont vides
 * @returns {boolean} true si la sauvegarde a réussi
 */
const saveInfo = (formData) => {
  try {
    const name = (formData.name || '').trim();
    const whatsapp = (formData.whatsapp || '').trim();
    const email = (formData.email || '').trim();
    // Ne pas sauvegarder si tous les champs sont vides
    if (!name && !whatsapp && !email) {
      return true; // Pas d'erreur, juste rien à sauvegarder
    }
    // V289 : mémoriser aussi la date de naissance (pré-remplissage à la prochaine visite).
    const toSave = { name, whatsapp, email, birthday: (formData.birthday || '').trim() };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
    // Vérification immédiate : relire pour confirmer
    const verify = localStorage.getItem(STORAGE_KEY);
    return verify !== null;
  } catch (err) {
    console.error('[SUBSCRIBER-FORM] localStorage ERREUR:', err);
    return false;
  }
};

/**
 * Supprime les données sauvegardées
 */
const clearSavedInfo = () => {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Silencieux
  }
};

/**
 * Formulaire d'identification pour les abonnés
 * @param {object} formData - Données du formulaire {name, whatsapp, email, code}
 * @param {function} setFormData - Setter pour mettre à jour les données
 * @param {function} onSubmit - Handler de soumission
 * @param {function} onCancel - Handler d'annulation (retour au chat visiteur)
 * @param {string} error - Message d'erreur à afficher
 * @param {boolean} isLoading - État de chargement (validation en cours)
 */
const SubscriberForm = ({
  formData,
  setFormData,
  onSubmit,
  onCancel,
  error,
  isLoading
}) => {
  // Toggle "Mémoriser" — TOUJOURS ON par défaut
  const [rememberMe, setRememberMe] = useState(true);
  // Feedback visuel : 'saved', 'restored', 'error', 'ls-unavailable', null
  const [saveStatus, setSaveStatus] = useState(null);
  // Ref pour accéder à rememberMe dans les handlers
  const rememberRef = React.useRef(true);
  rememberRef.current = rememberMe;
  // Ref pour accéder à formData à jour (éviter closures stale)
  const formDataRef = React.useRef(formData);
  formDataRef.current = formData;
  // Ref pour le timer du feedback
  const feedbackTimer = React.useRef(null);

  // Helper : afficher un feedback temporaire
  const showFeedback = useCallback((status) => {
    setSaveStatus(status);
    if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
    if (status !== 'ls-unavailable') {
      feedbackTimer.current = setTimeout(() => setSaveStatus(null), 3000);
    }
  }, []);

  // Diagnostic + auto-remplissage au montage
  useEffect(() => {
    // 1. Tester si localStorage est disponible
    const lsOk = isLocalStorageAvailable();
    console.log('[SUBSCRIBER-FORM] localStorage disponible:', lsOk);
    if (!lsOk) {
      showFeedback('ls-unavailable');
      return;
    }
    // 2. Nettoyer les données vides parasites
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && !(parsed.name || '').trim() && !(parsed.whatsapp || '').trim() && !(parsed.email || '').trim()) {
          localStorage.removeItem(STORAGE_KEY);
          console.log('[SUBSCRIBER-FORM] Nettoyage données vides parasites');
        }
      }
    } catch { /* silencieux */ }
    // 3. Charger les données sauvegardées (avec fallback profil)
    const saved = loadSavedInfo();
    if (saved) {
      console.log('[SUBSCRIBER-FORM] Auto-fill from localStorage:', JSON.stringify(saved));
      // V289 : recharger aussi la date de naissance mémorisée.
      let savedBirthday = '';
      try {
        const subInfo = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
        if (subInfo.birthday) savedBirthday = subInfo.birthday;
      } catch (e) {}
      setFormData(prev => ({
        ...prev,
        name: saved.name || prev.name,
        whatsapp: saved.whatsapp || prev.whatsapp,
        email: saved.email || prev.email,
        birthday: savedBirthday || prev.birthday || ''
      }));
      showFeedback('restored');
    } else {
      console.log('[SUBSCRIBER-FORM] Aucune donnée sauvegardée trouvée');
    }
  }, [setFormData, showFeedback]);

  /**
   * Handler de changement de champ — sauvegarde DIRECTE dans localStorage
   * Utilise formDataRef pour toujours avoir l'état le plus récent
   * (évite les closures stale lors de saisie rapide après restauration)
   */
  const handleFieldChange = useCallback((field, value) => {
    const updatedData = { ...formDataRef.current, [field]: value };
    setFormData(updatedData);
    // Sauvegarde directe et immédiate avec vérification
    if (rememberRef.current) {
      const success = saveInfo(updatedData);
      if (success) {
        showFeedback('saved');
      } else {
        showFeedback('error');
      }
    }
  }, [setFormData, showFeedback]);

  // Wrapper soumission
  const handleSubmit = useCallback((e) => {
    e.preventDefault();
    // V285/V289 : la date de naissance est OBLIGATOIRE et complète (jour+mois+année).
    const bday = (formData.birthday || '').trim();
    const bdayParts = bday.split('-');
    if (bdayParts.length !== 3 || !bdayParts[0] || !bdayParts[1] || !bdayParts[2]) {
      alert('La date de naissance est obligatoire (jour, mois et année).');
      return;
    }
    if (rememberMe) {
      saveInfo(formData);
    } else {
      clearSavedInfo();
    }
    // V285 : on persiste l'anniversaire au format MM-DD dans le profil local,
    // pour que le flux participantId du parent (endpoint birthday) puisse le
    // synchroniser. Le flux réservation persiste aussi le birthday par email.
    try {
      const parts = bday.split('-'); // YYYY-MM-DD
      if (parts.length === 3) {
        const mmdd = parts[1] + '-' + parts[2];
        const prof = JSON.parse(localStorage.getItem(PROFILE_KEY) || '{}');
        prof.birthday = mmdd;
        localStorage.setItem(PROFILE_KEY, JSON.stringify(prof));
      }
    } catch (err) { /* silencieux */ }
    onSubmit(e);
  }, [rememberMe, formData, onSubmit]);

  // Toggle handler
  const toggleRemember = useCallback(() => {
    setRememberMe(prev => {
      const next = !prev;
      if (next) {
        const success = saveInfo(formData);
        showFeedback(success ? 'saved' : 'error');
      } else {
        clearSavedInfo();
        showFeedback(null);
      }
      return next;
    });
  }, [formData, showFeedback]);

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        minHeight: 'min-content'
      }}
    >
      {/* Header */}
      <div style={{ textAlign: 'center', marginBottom: '8px' }}>
        <span style={{ fontSize: '28px' }}>💎</span>
        <p className="text-white text-sm mt-2">
          Identifiez-vous comme abonné
        </p>
        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', marginTop: '4px' }}>
          Accès à vos avantages et réservations rapides
        </p>
      </div>

      {/* Message d'erreur */}
      {error && (
        <div style={{
          background: 'rgba(239, 68, 68, 0.2)',
          color: '#ef4444',
          padding: '8px 12px',
          borderRadius: '8px',
          fontSize: '12px'
        }}>
          {error}
        </div>
      )}

      {/* Champ Nom */}
      <div>
        <label className="block text-white text-xs mb-1" style={{ opacity: 0.7 }}>Nom complet *</label>
        <input
          type="text"
          value={formData.name}
          onChange={(e) => handleFieldChange('name', e.target.value)}
          placeholder="Votre nom complet"
          className="w-full px-3 py-2 rounded-lg text-sm"
          style={{
            background: 'rgba(255,255,255,0.1)',
            border: '1px solid rgba(255,255,255,0.2)',
            color: '#fff',
            outline: 'none'
          }}
          data-testid="subscriber-name"
        />
      </div>

      {/* Champ WhatsApp */}
      <div>
        <label className="block text-white text-xs mb-1" style={{ opacity: 0.7 }}>Numéro WhatsApp *</label>
        <input
          type="tel"
          value={formData.whatsapp}
          onChange={(e) => handleFieldChange('whatsapp', e.target.value)}
          placeholder="+41 79 123 45 67"
          className="w-full px-3 py-2 rounded-lg text-sm"
          style={{
            background: 'rgba(255,255,255,0.1)',
            border: '1px solid rgba(255,255,255,0.2)',
            color: '#fff',
            outline: 'none'
          }}
          data-testid="subscriber-whatsapp"
        />
      </div>

      {/* Champ Email */}
      <div>
        <label className="block text-white text-xs mb-1" style={{ opacity: 0.7 }}>Email *</label>
        <input
          type="email"
          value={formData.email}
          onChange={(e) => handleFieldChange('email', e.target.value)}
          placeholder="votre@email.com"
          className="w-full px-3 py-2 rounded-lg text-sm"
          style={{
            background: 'rgba(255,255,255,0.1)',
            border: '1px solid rgba(255,255,255,0.2)',
            color: '#fff',
            outline: 'none'
          }}
          data-testid="subscriber-email"
        />
      </div>

      {/* Champ Code Promo */}
      <div>
        <label className="block text-white text-xs mb-1" style={{ opacity: 0.7 }}>Code Promo *</label>
        <input
          type="text"
          value={formData.code}
          onChange={(e) => handleFieldChange('code', e.target.value)}
          placeholder="Votre code abonné"
          className="w-full px-3 py-2 rounded-lg text-sm"
          style={{
            background: 'rgba(147, 51, 234, 0.2)',
            border: '1px solid rgba(147, 51, 234, 0.4)',
            color: '#fff',
            outline: 'none',
            textTransform: 'uppercase',
            fontWeight: '600',
            letterSpacing: '1px'
          }}
          data-testid="subscriber-code"
        />
      </div>

      {/* V289 : Date de naissance — 3 selects (Jour / Mois / Année), plus fiable
          que le calendrier natif. Stocké en YYYY-MM-DD dans formData.birthday. */}
      <div>
        <label className="block text-white text-xs mb-1" style={{ opacity: 0.7 }}>Date de naissance *</label>
        <div style={{ display: 'flex', gap: '8px' }}>
          <select
            value={(() => { const b = formData.birthday || ''; const p = b.split('-'); return p.length === 3 && p[2] ? String(parseInt(p[2], 10)) : ''; })()}
            onChange={(e) => { const p = (formData.birthday || '--').split('-'); handleFieldChange('birthday', (p[0] || '') + '-' + (p[1] || '') + '-' + (e.target.value ? e.target.value.padStart(2, '0') : '')); }}
            style={{ flex: 1, padding: '10px 6px', borderRadius: '10px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', fontSize: '14px', outline: 'none' }}
            data-testid="subscriber-birthday-day"
          >
            <option value="" style={{ background: '#1a1a2e' }}>Jour</option>
            {Array.from({ length: 31 }, (_, i) => i + 1).map(d => (<option key={d} value={String(d)} style={{ background: '#1a1a2e' }}>{d}</option>))}
          </select>
          <select
            value={(() => { const b = formData.birthday || ''; const p = b.split('-'); return p.length === 3 && p[1] ? String(parseInt(p[1], 10)) : ''; })()}
            onChange={(e) => { const p = (formData.birthday || '--').split('-'); handleFieldChange('birthday', (p[0] || '') + '-' + (e.target.value ? e.target.value.padStart(2, '0') : '') + '-' + (p[2] || '')); }}
            style={{ flex: 1.3, padding: '10px 6px', borderRadius: '10px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', fontSize: '14px', outline: 'none' }}
            data-testid="subscriber-birthday-month"
          >
            <option value="" style={{ background: '#1a1a2e' }}>Mois</option>
            {['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'].map((m, i) => (<option key={i + 1} value={String(i + 1)} style={{ background: '#1a1a2e' }}>{m}</option>))}
          </select>
          <select
            value={(() => { const b = formData.birthday || ''; const p = b.split('-'); return p.length === 3 && p[0] ? p[0] : ''; })()}
            onChange={(e) => { const p = (formData.birthday || '--').split('-'); handleFieldChange('birthday', (e.target.value || '') + '-' + (p[1] || '') + '-' + (p[2] || '')); }}
            style={{ flex: 1.1, padding: '10px 6px', borderRadius: '10px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', fontSize: '14px', outline: 'none' }}
            data-testid="subscriber-birthday-year"
          >
            <option value="" style={{ background: '#1a1a2e' }}>Année</option>
            {Array.from({ length: 80 }, (_, i) => new Date().getFullYear() - 10 - i).map(y => (<option key={y} value={String(y)} style={{ background: '#1a1a2e' }}>{y}</option>))}
          </select>
        </div>
        <p style={{ fontSize: '10px', color: '#aaa', marginTop: '4px', lineHeight: 1.3 }}>
          Pour recevoir un message le jour J ! Ton âge reste privé.
        </p>
      </div>

      {/* Toggle "Mémoriser mes informations" */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          padding: '10px 12px',
          background: rememberMe
            ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.15)'
            : 'rgba(255,255,255,0.05)',
          borderRadius: '10px',
          border: rememberMe
            ? '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.3)'
            : '1px solid rgba(255,255,255,0.1)',
          cursor: 'pointer',
          transition: 'all 0.3s ease',
          userSelect: 'none'
        }}
        onClick={toggleRemember}
        data-testid="remember-toggle-container"
      >
        {/* Switch custom */}
        <div style={{
          position: 'relative',
          width: '40px',
          height: '22px',
          flexShrink: 0,
          background: rememberMe
            ? 'linear-gradient(135deg, var(--primary-color, #D91CD2), #9333ea)'
            : 'rgba(255,255,255,0.2)',
          borderRadius: '11px',
          transition: 'background 0.3s ease',
          boxShadow: rememberMe ? '0 0 8px rgba(var(--primary-rgb, 217, 28, 210), 0.4)' : 'none'
        }}>
          <div style={{
            position: 'absolute',
            top: '2px',
            left: rememberMe ? '20px' : '2px',
            width: '18px',
            height: '18px',
            background: '#fff',
            borderRadius: '50%',
            transition: 'left 0.3s ease',
            boxShadow: '0 1px 3px rgba(0,0,0,0.3)'
          }} />
        </div>

        {/* Label + description */}
        <div style={{ flex: 1 }}>
          <span style={{
            color: rememberMe ? 'var(--primary-color, #D91CD2)' : 'rgba(255,255,255,0.7)',
            fontSize: '12px',
            fontWeight: '500',
            transition: 'color 0.3s ease'
          }}>
            Mémoriser mes informations
          </span>
          <p style={{
            color: saveStatus === 'saved' ? '#4ade80'
              : saveStatus === 'restored' ? '#60a5fa'
              : saveStatus === 'error' ? '#f87171'
              : saveStatus === 'ls-unavailable' ? '#fbbf24'
              : 'rgba(255,255,255,0.35)',
            fontSize: '10px',
            marginTop: '2px',
            lineHeight: '1.3',
            transition: 'color 0.3s ease'
          }}>
            {saveStatus === 'saved'
              ? '✅ Informations sauvegardées !'
              : saveStatus === 'restored'
              ? '✅ Informations restaurées depuis la mémoire'
              : saveStatus === 'error'
              ? '⚠️ Erreur de sauvegarde — navigation privée ?'
              : saveStatus === 'ls-unavailable'
              ? '⚠️ Stockage indisponible — navigation privée ou bloqué'
              : rememberMe
              ? '🔒 Nom, WhatsApp et Email sauvegardés sur cet appareil'
              : 'Pré-remplir le formulaire à votre prochaine visite'}
          </p>
        </div>
      </div>

      {/* Bouton de validation */}
      <button
        type="submit"
        disabled={isLoading}
        className="py-3 rounded-lg font-semibold text-sm transition-all"
        style={{
          background: 'linear-gradient(135deg, #9333ea, #6366f1)',
          color: '#fff',
          border: 'none',
          cursor: isLoading ? 'wait' : 'pointer',
          opacity: isLoading ? 0.7 : 1,
          marginTop: '8px'
        }}
        data-testid="subscriber-submit"
      >
        {isLoading ? '⏳ Validation...' : '💎 Valider mon abonnement'}
      </button>

      {/* Bouton retour */}
      <button
        type="button"
        onClick={onCancel}
        className="py-2 text-sm"
        style={{
          background: 'none',
          color: 'rgba(255,255,255,0.6)',
          border: 'none',
          cursor: 'pointer',
          textDecoration: 'underline'
        }}
        data-testid="back-to-visitor"
      >
        ← Retour au chat visiteur
      </button>
    </form>
  );
};

// Mémoïsation pour éviter les re-rendus inutiles
export default memo(SubscriberForm);

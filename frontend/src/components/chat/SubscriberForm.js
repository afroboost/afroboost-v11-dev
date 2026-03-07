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

/**
 * Charge les données sauvegardées depuis localStorage
 * @returns {object|null} {name, whatsapp, email} ou null
 */
const loadSavedInfo = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    // Validation: on accepte uniquement name, whatsapp, email
    if (parsed && typeof parsed === 'object' && (parsed.name || parsed.whatsapp || parsed.email)) {
      return {
        name: parsed.name || '',
        whatsapp: parsed.whatsapp || '',
        email: parsed.email || ''
      };
    }
    return null;
  } catch {
    return null;
  }
};

/**
 * Sauvegarde les infos dans localStorage (JAMAIS le code promo)
 */
const saveInfo = (formData) => {
  try {
    const toSave = {
      name: formData.name || '',
      whatsapp: formData.whatsapp || '',
      email: formData.email || ''
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
  } catch {
    // Silencieux si localStorage indisponible
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
  // Ref pour accéder à rememberMe dans les handlers sans re-render
  const rememberRef = React.useRef(true);
  rememberRef.current = rememberMe;

  // Auto-remplissage au montage si données sauvegardées
  useEffect(() => {
    const saved = loadSavedInfo();
    if (saved) {
      console.log('[SUBSCRIBER-FORM] Auto-fill from localStorage:', JSON.stringify(saved));
      setFormData(prev => ({
        ...prev,
        name: saved.name || prev.name,
        whatsapp: saved.whatsapp || prev.whatsapp,
        email: saved.email || prev.email
        // code: JAMAIS pré-rempli
      }));
    } else {
      console.log('[SUBSCRIBER-FORM] No saved data found in localStorage');
    }
  }, [setFormData]);

  /**
   * Handler de changement de champ — sauvegarde DIRECTE dans localStorage
   * Pas de useEffect, pas de dépendances, pas de closures stales.
   */
  const handleFieldChange = useCallback((field, value) => {
    const updatedData = { ...formData, [field]: value };
    setFormData(updatedData);
    // Sauvegarde directe et immédiate
    if (rememberRef.current) {
      saveInfo(updatedData);
      console.log('[SUBSCRIBER-FORM] Direct save:', field, '→', value.substring(0, 20));
    }
  }, [formData, setFormData]);

  // Wrapper soumission
  const handleSubmit = useCallback((e) => {
    e.preventDefault();
    if (rememberMe) {
      saveInfo(formData);
      console.log('[SUBSCRIBER-FORM] Save on submit');
    } else {
      clearSavedInfo();
      console.log('[SUBSCRIBER-FORM] Clear on submit (toggle OFF)');
    }
    onSubmit(e);
  }, [rememberMe, formData, onSubmit]);

  // Toggle handler
  const toggleRemember = useCallback(() => {
    setRememberMe(prev => {
      const next = !prev;
      if (next) {
        saveInfo(formData);
        console.log('[SUBSCRIBER-FORM] Toggle ON → saved');
      } else {
        clearSavedInfo();
        console.log('[SUBSCRIBER-FORM] Toggle OFF → cleared');
      }
      return next;
    });
  }, [formData]);

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
          onChange={(e) => handleFieldChange('code', e.target.value.toUpperCase())}
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

      {/* Toggle "Mémoriser mes informations" */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          padding: '10px 12px',
          background: rememberMe
            ? 'rgba(147, 51, 234, 0.15)'
            : 'rgba(255,255,255,0.05)',
          borderRadius: '10px',
          border: rememberMe
            ? '1px solid rgba(147, 51, 234, 0.3)'
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
            ? 'linear-gradient(135deg, #9333ea, #6366f1)'
            : 'rgba(255,255,255,0.2)',
          borderRadius: '11px',
          transition: 'background 0.3s ease',
          boxShadow: rememberMe ? '0 0 8px rgba(147, 51, 234, 0.4)' : 'none'
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
            color: rememberMe ? '#c084fc' : 'rgba(255,255,255,0.7)',
            fontSize: '12px',
            fontWeight: '500',
            transition: 'color 0.3s ease'
          }}>
            Mémoriser mes informations
          </span>
          <p style={{
            color: 'rgba(255,255,255,0.35)',
            fontSize: '10px',
            marginTop: '2px',
            lineHeight: '1.3'
          }}>
            {rememberMe
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

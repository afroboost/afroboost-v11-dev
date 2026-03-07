/**
 * BrandingManager Component v17.0
 * Gestion couleur accent + logo du coach
 */
import React, { useState, useEffect, useCallback } from 'react';

const BrandingManager = ({ API, coachEmail, t }) => {
  const [accentColor, setAccentColor] = useState('#D91CD2');
  const [logoUrl, setLogoUrl] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState(null);

  // Charger le branding actuel
  useEffect(() => {
    if (!coachEmail) return;
    fetch(`${API}/coach/branding/${coachEmail}`)
      .then(r => r.json())
      .then(data => {
        if (data.accent_color) setAccentColor(data.accent_color);
        if (data.logo_url) setLogoUrl(data.logo_url);
      })
      .catch(() => {});
  }, [API, coachEmail]);

  const saveBranding = useCallback(async (color, logo) => {
    setSaving(true);
    setSaveStatus(null);
    try {
      const res = await fetch(`${API}/coach/update-branding`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-Email': coachEmail },
        body: JSON.stringify({ accent_color: color, logo_url: logo })
      });
      if (res.ok) {
        setSaveStatus('saved');
        setTimeout(() => setSaveStatus(null), 2000);
      } else {
        setSaveStatus('error');
      }
    } catch {
      setSaveStatus('error');
    } finally {
      setSaving(false);
    }
  }, [API, coachEmail]);

  const handleColorChange = (e) => {
    const color = e.target.value;
    setAccentColor(color);
  };

  const handleSave = () => {
    saveBranding(accentColor, logoUrl);
  };

  return (
    <div style={{
      background: 'rgba(139, 92, 246, 0.05)',
      border: '1px solid rgba(139, 92, 246, 0.2)',
      borderRadius: '12px',
      padding: '20px',
      marginTop: '16px'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
        <h3 style={{ color: '#fff', fontWeight: 600, fontSize: '16px', margin: 0 }}>
          🎨 Branding
        </h3>
        {saveStatus && (
          <span style={{
            fontSize: '12px',
            padding: '4px 10px',
            borderRadius: '20px',
            background: saveStatus === 'saved' ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)',
            color: saveStatus === 'saved' ? '#22c55e' : '#ef4444',
            border: `1px solid ${saveStatus === 'saved' ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`
          }}>
            {saveStatus === 'saved' ? '✓ Sauvegardé' : '✕ Erreur'}
          </span>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        {/* Couleur accent */}
        <div>
          <label style={{ display: 'block', color: 'rgba(255,255,255,0.6)', fontSize: '12px', marginBottom: '8px' }}>
            Couleur accent
          </label>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <input
              type="color"
              value={accentColor}
              onChange={handleColorChange}
              style={{
                width: '48px',
                height: '48px',
                border: 'none',
                borderRadius: '10px',
                cursor: 'pointer',
                background: 'transparent',
                padding: 0
              }}
              data-testid="branding-color"
            />
            <div>
              <div style={{
                width: '60px',
                height: '30px',
                borderRadius: '6px',
                background: accentColor,
                border: '1px solid rgba(255,255,255,0.2)'
              }} />
              <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px', marginTop: '4px', display: 'block' }}>
                {accentColor}
              </span>
            </div>
          </div>
        </div>

        {/* Logo URL */}
        <div>
          <label style={{ display: 'block', color: 'rgba(255,255,255,0.6)', fontSize: '12px', marginBottom: '8px' }}>
            Logo URL
          </label>
          <input
            type="url"
            value={logoUrl}
            onChange={(e) => setLogoUrl(e.target.value)}
            placeholder="https://..."
            style={{
              width: '100%',
              padding: '10px 12px',
              borderRadius: '8px',
              background: 'rgba(139, 92, 246, 0.1)',
              border: '1px solid rgba(139, 92, 246, 0.3)',
              color: '#fff',
              fontSize: '13px',
              outline: 'none'
            }}
            data-testid="branding-logo"
          />
          {logoUrl && (
            <div style={{ marginTop: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <img
                src={logoUrl}
                alt="Logo preview"
                style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '8px',
                  objectFit: 'contain',
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(255,255,255,0.1)'
                }}
                onError={(e) => { e.target.style.display = 'none'; }}
              />
              <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '11px' }}>Aperçu</span>
            </div>
          )}
        </div>
      </div>

      {/* Preview */}
      <div style={{
        marginTop: '16px',
        padding: '12px',
        borderRadius: '8px',
        background: 'rgba(0,0,0,0.3)',
        border: `1px solid ${accentColor}33`
      }}>
        <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px', display: 'block', marginBottom: '8px' }}>
          Aperçu vitrine
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {logoUrl && (
            <img src={logoUrl} alt="" style={{ width: '32px', height: '32px', borderRadius: '6px', objectFit: 'contain' }}
              onError={(e) => { e.target.style.display = 'none'; }} />
          )}
          <button style={{
            background: accentColor,
            color: '#fff',
            padding: '8px 20px',
            borderRadius: '8px',
            border: 'none',
            fontWeight: 600,
            fontSize: '13px',
            cursor: 'default'
          }}>
            Réserver
          </button>
          <span style={{ color: accentColor, fontSize: '13px', fontWeight: 600 }}>Lien accent</span>
        </div>
      </div>

      <button
        onClick={handleSave}
        disabled={saving}
        style={{
          marginTop: '16px',
          width: '100%',
          padding: '10px',
          borderRadius: '8px',
          background: saving ? 'rgba(139,92,246,0.3)' : 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
          color: '#fff',
          fontWeight: 600,
          fontSize: '14px',
          border: 'none',
          cursor: saving ? 'wait' : 'pointer'
        }}
        data-testid="save-branding"
      >
        {saving ? '⏳ Sauvegarde...' : '💾 Sauvegarder le branding'}
      </button>
    </div>
  );
};

export default BrandingManager;

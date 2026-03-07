/**
 * SEOManager Component v17.1
 * Gestion SEO: meta title, description, keywords + IA + preview Google
 */
import React, { useState, useEffect, useCallback } from 'react';

const SEOManager = ({ API, coachEmail, coachUsername, t }) => {
  const [metaTitle, setMetaTitle] = useState('');
  const [metaDescription, setMetaDescription] = useState('');
  const [seoKeywords, setSeoKeywords] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);

  useEffect(() => {
    if (!coachEmail) return;
    fetch(`${API}/coach/seo/${coachEmail}`)
      .then(r => r.json())
      .then(data => {
        if (data.meta_title) setMetaTitle(data.meta_title);
        if (data.meta_description) setMetaDescription(data.meta_description);
        if (data.seo_keywords) setSeoKeywords(data.seo_keywords);
      })
      .catch(() => {});
  }, [API, coachEmail]);

  const saveSEO = useCallback(async () => {
    setSaving(true);
    setSaveStatus(null);
    try {
      const res = await fetch(`${API}/coach/update-seo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-Email': coachEmail },
        body: JSON.stringify({ meta_title: metaTitle, meta_description: metaDescription, seo_keywords: seoKeywords })
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
  }, [API, coachEmail, metaTitle, metaDescription, seoKeywords]);

  const handleAISEO = async () => {
    const text = `Titre: ${metaTitle || 'Coach fitness'}\nDescription: ${metaDescription || 'Page coach'}\nMots-clés: ${seoKeywords || 'fitness, coaching'}`;
    setAiLoading(true);
    try {
      const res = await fetch(`${API}/ai/enhance-text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, context: 'seo' })
      });
      const data = await res.json();
      if (data.enhanced_text && !data.fallback) {
        // Parse AI response — try to extract title / description / keywords
        const lines = data.enhanced_text.split('\n').filter(l => l.trim());
        for (const line of lines) {
          const lower = line.toLowerCase();
          if (lower.startsWith('titre') || lower.startsWith('title')) {
            const val = line.split(':').slice(1).join(':').trim().replace(/^["']|["']$/g, '');
            if (val) setMetaTitle(val.slice(0, 60));
          } else if (lower.startsWith('desc')) {
            const val = line.split(':').slice(1).join(':').trim().replace(/^["']|["']$/g, '');
            if (val) setMetaDescription(val.slice(0, 160));
          } else if (lower.startsWith('mot') || lower.startsWith('key')) {
            const val = line.split(':').slice(1).join(':').trim();
            if (val) setSeoKeywords(val);
          }
        }
        // If parsing failed, use as description
        if (lines.length === 1) {
          setMetaDescription(data.enhanced_text.slice(0, 160));
        }
      }
    } catch (err) {
      console.error('[AI SEO]', err);
    } finally {
      setAiLoading(false);
    }
  };

  const vitrineUrl = coachUsername
    ? `https://afroboost-v11-dev-pm7l.vercel.app/coach/${coachUsername}`
    : '';

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
          🔍 SEO & Référencement
        </h3>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button
            type="button"
            onClick={handleAISEO}
            disabled={aiLoading}
            style={{
              fontSize: '12px',
              padding: '4px 10px',
              borderRadius: '8px',
              background: aiLoading ? 'rgba(139,92,246,0.2)' : 'rgba(217,28,210,0.2)',
              border: '1px solid rgba(217,28,210,0.4)',
              color: '#D91CD2',
              cursor: aiLoading ? 'wait' : 'pointer'
            }}
            data-testid="ai-enhance-seo"
          >
            {aiLoading ? '⏳ IA...' : '✨ Optimiser SEO avec IA'}
          </button>
          {saveStatus && (
            <span style={{
              fontSize: '12px',
              padding: '4px 10px',
              borderRadius: '20px',
              background: saveStatus === 'saved' ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)',
              color: saveStatus === 'saved' ? '#22c55e' : '#ef4444'
            }}>
              {saveStatus === 'saved' ? '✓ Sauvé' : '✕ Erreur'}
            </span>
          )}
        </div>
      </div>

      {/* Meta Title */}
      <div style={{ marginBottom: '12px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
          <label style={{ color: 'rgba(255,255,255,0.6)', fontSize: '12px' }}>Meta Title (max 60)</label>
          <span style={{ color: metaTitle.length > 60 ? '#ef4444' : 'rgba(255,255,255,0.3)', fontSize: '11px' }}>
            {metaTitle.length}/60
          </span>
        </div>
        <input
          type="text"
          value={metaTitle}
          onChange={(e) => setMetaTitle(e.target.value.slice(0, 70))}
          placeholder="Coach Fitness | Votre Nom | Afroboost"
          style={{
            width: '100%', padding: '10px 12px', borderRadius: '8px',
            background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)',
            color: '#fff', fontSize: '13px', outline: 'none'
          }}
          data-testid="seo-meta-title"
        />
      </div>

      {/* Meta Description */}
      <div style={{ marginBottom: '12px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
          <label style={{ color: 'rgba(255,255,255,0.6)', fontSize: '12px' }}>Meta Description (max 160)</label>
          <span style={{ color: metaDescription.length > 160 ? '#ef4444' : 'rgba(255,255,255,0.3)', fontSize: '11px' }}>
            {metaDescription.length}/160
          </span>
        </div>
        <textarea
          value={metaDescription}
          onChange={(e) => setMetaDescription(e.target.value.slice(0, 170))}
          placeholder="Découvrez mes cours de fitness, danse et coaching personnalisé..."
          rows={2}
          style={{
            width: '100%', padding: '10px 12px', borderRadius: '8px',
            background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)',
            color: '#fff', fontSize: '13px', outline: 'none', resize: 'none'
          }}
          data-testid="seo-meta-description"
        />
      </div>

      {/* Keywords */}
      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', color: 'rgba(255,255,255,0.6)', fontSize: '12px', marginBottom: '4px' }}>
          Mots-clés (séparés par virgules)
        </label>
        <input
          type="text"
          value={seoKeywords}
          onChange={(e) => setSeoKeywords(e.target.value)}
          placeholder="fitness, danse, coaching, Genève, afro..."
          style={{
            width: '100%', padding: '10px 12px', borderRadius: '8px',
            background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)',
            color: '#fff', fontSize: '13px', outline: 'none'
          }}
          data-testid="seo-keywords"
        />
      </div>

      {/* Google Preview */}
      <div style={{
        padding: '12px 16px', borderRadius: '8px',
        background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
        marginBottom: '16px'
      }}>
        <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '11px', display: 'block', marginBottom: '8px' }}>
          Aperçu Google
        </span>
        <div style={{ color: '#8ab4f8', fontSize: '16px', marginBottom: '2px', textDecoration: 'none' }}>
          {metaTitle || 'Titre de votre page'}
        </div>
        <div style={{ color: '#bdc1c6', fontSize: '12px', marginBottom: '4px' }}>
          {vitrineUrl || 'https://afroboost.com/coach/votre-nom'}
        </div>
        <div style={{ color: '#9aa0a6', fontSize: '13px', lineHeight: '1.4' }}>
          {metaDescription || 'Description de votre page qui apparaîtra dans les résultats de recherche...'}
        </div>
      </div>

      <button
        onClick={saveSEO}
        disabled={saving}
        style={{
          width: '100%', padding: '10px', borderRadius: '8px',
          background: saving ? 'rgba(139,92,246,0.3)' : 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
          color: '#fff', fontWeight: 600, fontSize: '14px', border: 'none',
          cursor: saving ? 'wait' : 'pointer'
        }}
        data-testid="save-seo"
      >
        {saving ? '⏳ Sauvegarde...' : '💾 Sauvegarder SEO'}
      </button>
    </div>
  );
};

export default SEOManager;

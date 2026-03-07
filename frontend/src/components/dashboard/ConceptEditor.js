/**
 * ConceptEditor Component v13.4
 * Éditeur de concept/personnalisation - Extrait de CoachDashboard.js
 */
import React from 'react';
import { LandingSectionSelector } from '../SearchBar';

const ConceptEditor = ({
  concept,
  setConcept,
  conceptSaveStatus,
  saveConcept,
  API,
  t,
  isSuperAdmin = false,
  coachEmail = ''
}) => {
  const [aiLegalLoading, setAiLegalLoading] = React.useState(false);
  const [uploadingVideo, setUploadingVideo] = React.useState(null); // slot index being uploaded

  // Helper: get heroVideos array (with migration from legacy heroImageUrl)
  const getHeroVideos = () => {
    if (concept.heroVideos && concept.heroVideos.length > 0) return concept.heroVideos;
    if (concept.heroImageUrl) return [{ url: concept.heroImageUrl, type: 'youtube', title: '' }];
    return [];
  };

  const updateHeroVideo = (index, field, value) => {
    const videos = [...getHeroVideos()];
    if (videos[index]) {
      videos[index] = { ...videos[index], [field]: value };
    }
    setConcept({ ...concept, heroVideos: videos, heroImageUrl: videos[0]?.url || '' });
  };

  const addHeroVideo = () => {
    const videos = [...getHeroVideos()];
    if (videos.length >= 3) return;
    videos.push({ url: '', type: 'youtube', title: '' });
    setConcept({ ...concept, heroVideos: videos });
  };

  const removeHeroVideo = (index) => {
    const videos = [...getHeroVideos()];
    videos.splice(index, 1);
    setConcept({ ...concept, heroVideos: videos, heroImageUrl: videos[0]?.url || '' });
  };

  const handleVideoUpload = async (file, slotIndex) => {
    if (!file || !isSuperAdmin) return;
    setUploadingVideo(slotIndex);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('asset_type', 'video');
      const res = await fetch(`${API}/coach/upload-asset`, {
        method: 'POST',
        headers: { 'X-User-Email': coachEmail },
        body: formData
      });
      const data = await res.json();
      if (data.url) {
        const videos = [...getHeroVideos()];
        videos[slotIndex] = { url: data.url, type: 'upload', title: file.name.replace(/\.[^.]+$/, '') };
        setConcept({ ...concept, heroVideos: videos, heroImageUrl: videos[0]?.url || '' });
      }
    } catch (err) {
      console.error('Erreur upload vidéo:', err);
      alert('Erreur lors de l\'upload de la vidéo');
    } finally {
      setUploadingVideo(null);
    }
  };

  const handleAILegal = async () => {
    const text = concept.termsText;
    if (!text || text.trim().length < 10) return;
    setAiLegalLoading(true);
    try {
      const res = await fetch(`${API}/ai/enhance-text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, context: 'legal' })
      });
      const data = await res.json();
      if (data.enhanced_text && !data.fallback) {
        setConcept({ ...concept, termsText: data.enhanced_text });
      }
    } catch (err) {
      console.error('[AI Legal]', err);
    } finally {
      setAiLegalLoading(false);
    }
  };
  return (
    <div className="card-gradient rounded-xl p-6">
      {/* Indicateur de sauvegarde automatique */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-semibold text-white" style={{ fontSize: '20px' }}>{t('conceptVisual')}</h2>
        {conceptSaveStatus && (
          <span 
            className="px-3 py-1 rounded-full text-xs font-medium flex items-center gap-2"
            style={{
              background: conceptSaveStatus === 'saved' ? 'rgba(34, 197, 94, 0.2)' : 
                         conceptSaveStatus === 'error' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(147, 51, 234, 0.2)',
              color: conceptSaveStatus === 'saved' ? '#22c55e' : 
                     conceptSaveStatus === 'error' ? '#ef4444' : '#a855f7',
              border: `1px solid ${conceptSaveStatus === 'saved' ? 'rgba(34, 197, 94, 0.3)' : 
                      conceptSaveStatus === 'error' ? 'rgba(239, 68, 68, 0.3)' : 'rgba(147, 51, 234, 0.3)'}`
            }}
            data-testid="concept-save-status"
          >
            {conceptSaveStatus === 'saving' && <><span className="animate-spin">⏳</span> Sauvegarde...</>}
            {conceptSaveStatus === 'saved' && <>✓ Sauvegardé</>}
            {conceptSaveStatus === 'error' && <>⚠️ Erreur</>}
          </span>
        )}
      </div>
      
      <div className="space-y-4">
        {/* PERSONNALISATION DES COULEURS */}
        <div className="border border-purple-500/30 rounded-lg p-4 bg-purple-900/10">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-purple-400 font-semibold">🎨 Personnalisation des couleurs</h3>
            <button
              onClick={saveConcept}
              className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover:scale-105"
              style={{
                background: 'linear-gradient(135deg, var(--primary-color, #D91CD2), var(--secondary-color, #8b5cf6))',
                color: 'white'
              }}
              data-testid="save-colors-btn"
            >
              💾 Sauvegarder
            </button>
          </div>
          <p className="text-white/60 text-xs mb-4">Les modifications s'appliquent en temps réel et sont auto-sauvegardées après 1 seconde.</p>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {/* Couleur principale */}
            <div>
              <label className="block mb-2 text-white text-sm">✨ Couleur principale (Boutons/Titres)</label>
              <div className="flex items-center gap-3">
                <input 
                  type="color" 
                  value={concept.primaryColor || '#D91CD2'} 
                  onChange={(e) => {
                    const newColor = e.target.value;
                    setConcept({ ...concept, primaryColor: newColor });
                    document.documentElement.style.setProperty('--primary-color', newColor);
                    if (!concept.glowColor) {
                      document.documentElement.style.setProperty('--glow-color', `${newColor}66`);
                      document.documentElement.style.setProperty('--glow-color-strong', `${newColor}99`);
                    }
                  }}
                  className="w-12 h-12 rounded-lg cursor-pointer border-2 border-white/20"
                  style={{ background: 'transparent' }}
                  data-testid="color-picker-primary"
                />
                <div>
                  <input 
                    type="text" 
                    value={concept.primaryColor || '#D91CD2'} 
                    onChange={(e) => {
                      const newColor = e.target.value;
                      if (/^#[0-9A-Fa-f]{6}$/.test(newColor)) {
                        setConcept({ ...concept, primaryColor: newColor });
                        document.documentElement.style.setProperty('--primary-color', newColor);
                        if (!concept.glowColor) {
                          document.documentElement.style.setProperty('--glow-color', `${newColor}66`);
                        }
                      }
                    }}
                    className="px-3 py-2 rounded-lg neon-input text-sm uppercase w-28"
                    placeholder="#D91CD2"
                  />
                  <p className="text-xs mt-1 text-white/40">Rose par défaut</p>
                </div>
              </div>
            </div>
            
            {/* Couleur secondaire */}
            <div>
              <label className="block mb-2 text-white text-sm">💜 Couleur secondaire (Accents)</label>
              <div className="flex items-center gap-3">
                <input 
                  type="color" 
                  value={concept.secondaryColor || '#8b5cf6'} 
                  onChange={(e) => {
                    const newColor = e.target.value;
                    setConcept({ ...concept, secondaryColor: newColor });
                    document.documentElement.style.setProperty('--secondary-color', newColor);
                  }}
                  className="w-12 h-12 rounded-lg cursor-pointer border-2 border-white/20"
                  style={{ background: 'transparent' }}
                  data-testid="color-picker-secondary"
                />
                <div>
                  <input 
                    type="text" 
                    value={concept.secondaryColor || '#8b5cf6'} 
                    onChange={(e) => {
                      const newColor = e.target.value;
                      if (/^#[0-9A-Fa-f]{6}$/.test(newColor)) {
                        setConcept({ ...concept, secondaryColor: newColor });
                        document.documentElement.style.setProperty('--secondary-color', newColor);
                      }
                    }}
                    className="px-3 py-2 rounded-lg neon-input text-sm uppercase w-28"
                    placeholder="#8b5cf6"
                  />
                  <p className="text-xs mt-1 text-white/40">Violet par défaut</p>
                </div>
              </div>
            </div>
            
            {/* Couleur de fond */}
            <div>
              <label className="block mb-2 text-white text-sm">🌑 Couleur de fond (Background)</label>
              <div className="flex items-center gap-3">
                <input 
                  type="color" 
                  value={concept.backgroundColor || '#000000'} 
                  onChange={(e) => {
                    const newColor = e.target.value;
                    setConcept({ ...concept, backgroundColor: newColor });
                    document.documentElement.style.setProperty('--background-color', newColor);
                    document.body.style.backgroundColor = newColor;
                  }}
                  className="w-12 h-12 rounded-lg cursor-pointer border-2 border-white/20"
                  style={{ background: 'transparent' }}
                  data-testid="color-picker-background"
                />
                <div>
                  <input 
                    type="text" 
                    value={concept.backgroundColor || '#000000'} 
                    onChange={(e) => {
                      const newColor = e.target.value;
                      if (/^#[0-9A-Fa-f]{6}$/.test(newColor)) {
                        setConcept({ ...concept, backgroundColor: newColor });
                        document.documentElement.style.setProperty('--background-color', newColor);
                        document.body.style.backgroundColor = newColor;
                      }
                    }}
                    className="px-3 py-2 rounded-lg neon-input text-sm uppercase w-28"
                    placeholder="#000000"
                  />
                  <p className="text-xs mt-1 text-white/40">Noir par défaut</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* PARAMÈTRES GÉNÉRAUX */}
        <div className="border border-purple-500/30 rounded-lg p-4 bg-purple-900/10">
          <h3 className="text-purple-400 font-semibold mb-4">⚙️ Paramètres généraux</h3>
          
          {/* Nom de l'application */}
          <div className="mb-4">
            <label className="block mb-1 text-white text-xs opacity-70">{t('appName')}</label>
            <input 
              type="text" 
              value={concept.appName} 
              onChange={(e) => setConcept({ ...concept, appName: e.target.value })}
              className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
            />
          </div>
          
          {/* Description */}
          <div className="mb-4">
            <label className="block mb-1 text-white text-xs opacity-70">{t('description')}</label>
            <textarea 
              value={concept.description} 
              onChange={(e) => setConcept({ ...concept, description: e.target.value })}
              className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
              rows={3}
            />
          </div>
          
          {/* v18: Multi-Vidéos Héro (3 max) */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <label className="text-white text-xs opacity-70">🎬 Vidéos Héro (max 3)</label>
              {getHeroVideos().length < 3 && (
                <button
                  type="button"
                  onClick={addHeroVideo}
                  style={{
                    background: 'rgba(217,28,210,0.2)', border: '1px solid rgba(217,28,210,0.4)',
                    color: '#D91CD2', fontSize: '11px', padding: '3px 10px', borderRadius: '8px', cursor: 'pointer'
                  }}
                >+ Ajouter une vidéo</button>
              )}
            </div>
            {getHeroVideos().length === 0 && (
              <div
                onClick={addHeroVideo}
                style={{
                  border: '2px dashed rgba(217,28,210,0.3)', borderRadius: '12px', padding: '20px',
                  textAlign: 'center', cursor: 'pointer', background: 'rgba(217,28,210,0.04)'
                }}
              >
                <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px' }}>
                  Cliquez pour ajouter votre première vidéo héro
                </p>
              </div>
            )}
            {getHeroVideos().map((video, idx) => (
              <div key={idx} style={{
                background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: '10px', padding: '12px', marginBottom: '8px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ color: '#D91CD2', fontSize: '12px', fontWeight: 600 }}>Vidéo {idx + 1}</span>
                  <button
                    type="button"
                    onClick={() => removeHeroVideo(idx)}
                    style={{ background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444', fontSize: '11px', padding: '2px 8px', borderRadius: '6px', cursor: 'pointer' }}
                  >Retirer</button>
                </div>
                <input
                  type="url"
                  value={video.url || ''}
                  onChange={(e) => {
                    const url = e.target.value;
                    const isYT = url.includes('youtube.com') || url.includes('youtu.be');
                    const isVimeo = url.includes('vimeo.com');
                    updateHeroVideo(idx, 'url', url);
                    if (isYT) updateHeroVideo(idx, 'type', 'youtube');
                    else if (isVimeo) updateHeroVideo(idx, 'type', 'vimeo');
                  }}
                  className="w-full px-3 py-2 rounded-lg neon-input text-sm"
                  placeholder="Lien YouTube ou Vimeo (ex: https://youtu.be/...)"
                  style={{ marginBottom: '6px' }}
                />
                {isSuperAdmin && (
                  <div style={{ marginTop: '4px' }}>
                    <label
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: '6px', cursor: 'pointer',
                        background: 'rgba(139,92,246,0.15)', border: '1px solid rgba(139,92,246,0.3)',
                        padding: '4px 10px', borderRadius: '8px', fontSize: '11px', color: '#a78bfa'
                      }}
                    >
                      {uploadingVideo === idx ? '⏳ Upload...' : '📁 Upload fichier (MP4/MOV)'}
                      <input
                        type="file"
                        accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm"
                        style={{ display: 'none' }}
                        onChange={(e) => { if (e.target.files[0]) handleVideoUpload(e.target.files[0], idx); }}
                        disabled={uploadingVideo !== null}
                      />
                    </label>
                    <span style={{ fontSize: '10px', color: 'rgba(255,255,255,0.3)', marginLeft: '6px' }}>
                      Admin uniquement — max 15MB
                    </span>
                  </div>
                )}
                {video.url && (video.url.includes('youtu') || video.url.includes('vimeo')) && (
                  <div style={{ marginTop: '6px', borderRadius: '8px', overflow: 'hidden', maxWidth: '240px' }}>
                    <div style={{ position: 'relative', paddingBottom: '56.25%', height: 0 }}>
                      <iframe
                        src={video.url.includes('youtu')
                          ? `https://www.youtube.com/embed/${video.url.match(/(?:youtube\.com\/(?:watch\?v=|embed\/|v\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/)?.[1] || ''}`
                          : `https://player.vimeo.com/video/${video.url.split('/').pop()}`
                        }
                        style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', border: 'none' }}
                        allow="autoplay; encrypted-media"
                        allowFullScreen
                        title={`Preview vidéo ${idx + 1}`}
                      />
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
          
          {/* Logo URL */}
          <div className="mb-4">
            <label className="block mb-1 text-white text-xs opacity-70">{t('logoUrl')}</label>
            <input 
              type="url" 
              value={concept.logoUrl || ''} 
              onChange={(e) => setConcept({ ...concept, logoUrl: e.target.value })}
              className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
              placeholder="https://..."
            />
          </div>
          
          {/* Favicon URL */}
          <div className="mb-4">
            <label className="block mb-1 text-white text-xs opacity-70">Favicon URL</label>
            <input 
              type="url" 
              value={concept.faviconUrl || ''} 
              onChange={(e) => setConcept({ ...concept, faviconUrl: e.target.value })}
              className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
              placeholder="https://..."
            />
          </div>
          
          {/* Conditions générales */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-1">
              <label className="text-white text-xs opacity-70">{t('termsText')}</label>
              <button
                type="button"
                onClick={handleAILegal}
                disabled={aiLegalLoading || !(concept.termsText?.trim()?.length >= 10)}
                className="text-xs px-2 py-1 rounded-lg"
                style={{
                  background: aiLegalLoading ? 'rgba(139,92,246,0.2)' : 'rgba(217,28,210,0.2)',
                  border: '1px solid rgba(217,28,210,0.4)',
                  color: '#D91CD2',
                  cursor: aiLegalLoading ? 'wait' : 'pointer',
                  opacity: !(concept.termsText?.trim()?.length >= 10) ? 0.4 : 1
                }}
                data-testid="ai-enhance-legal"
              >
                {aiLegalLoading ? '⏳ IA...' : '✨ Aide IA'}
              </button>
            </div>
            <textarea
              value={concept.termsText}
              onChange={(e) => setConcept({ ...concept, termsText: e.target.value })}
              className="w-full px-3 py-2 rounded-lg neon-input text-sm"
              rows={4}
            />
          </div>
          
          {/* Lien Google Reviews */}
          <div className="mb-4">
            <label className="block mb-1 text-white text-xs opacity-70">Lien Google Reviews</label>
            <input 
              type="url" 
              value={concept.googleReviewsUrl || ''} 
              onChange={(e) => setConcept({ ...concept, googleReviewsUrl: e.target.value })}
              className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
              placeholder="https://g.page/..."
              data-testid="google-reviews-url"
            />
            {concept.googleReviewsUrl && (
              <div className="mt-2">
                <a 
                  href={concept.googleReviewsUrl} 
                  target="_blank" 
                  rel="noopener noreferrer" 
                  className="text-xs text-pink-400 hover:text-pink-300 underline"
                >
                  Tester le lien
                </a>
              </div>
            )}
          </div>
        </div>

        {/* Section d'atterrissage */}
        <div className="border-t border-purple-500/30 pt-6">
          <LandingSectionSelector 
            value={concept.defaultLandingSection || 'sessions'}
            onChange={(value) => setConcept({ ...concept, defaultLandingSection: value })}
          />
        </div>

        {/* Liens Externes */}
        <div className="border-t border-purple-500/30 pt-6">
          <h3 className="text-white text-sm font-semibold mb-4">🔗 Liens Externes (affichés en bas de page)</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block mb-1 text-white text-xs opacity-70">Titre du lien 1</label>
              <input 
                type="text" 
                value={concept.externalLink1Title || ''} 
                onChange={(e) => setConcept({ ...concept, externalLink1Title: e.target.value })}
                className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
                placeholder="Ex: Instagram"
                data-testid="external-link1-title"
              />
            </div>
            <div>
              <label className="block mb-1 text-white text-xs opacity-70">URL du lien 1</label>
              <input 
                type="url" 
                value={concept.externalLink1Url || ''} 
                onChange={(e) => setConcept({ ...concept, externalLink1Url: e.target.value })}
                className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
                placeholder="https://..."
                data-testid="external-link1-url"
              />
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block mb-1 text-white text-xs opacity-70">Titre du lien 2</label>
              <input 
                type="text" 
                value={concept.externalLink2Title || ''} 
                onChange={(e) => setConcept({ ...concept, externalLink2Title: e.target.value })}
                className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
                placeholder="Ex: Facebook"
                data-testid="external-link2-title"
              />
            </div>
            <div>
              <label className="block mb-1 text-white text-xs opacity-70">URL du lien 2</label>
              <input 
                type="url" 
                value={concept.externalLink2Url || ''} 
                onChange={(e) => setConcept({ ...concept, externalLink2Url: e.target.value })}
                className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
                placeholder="https://..."
                data-testid="external-link2-url"
              />
            </div>
          </div>
        </div>

        {/* Logos de paiement */}
        <div className="border-t border-purple-500/30 pt-6">
          <h3 className="text-white text-sm font-semibold mb-4">💳 Logos de paiement</h3>
          <p className="text-xs mb-4" style={{ color: 'rgba(255,255,255,0.4)' }}>
            Activez les logos qui s'afficheront dans le pied de page.
          </p>
          <div className="space-y-3">
            {/* Toggle Twint */}
            <div className="flex items-center justify-between p-3 rounded-lg" style={{ background: 'rgba(139, 92, 246, 0.1)' }}>
              <div className="flex items-center gap-3">
                <div style={{ background: '#00A9E0', borderRadius: '4px', padding: '2px 6px', display: 'flex', alignItems: 'center' }}>
                  <span style={{ color: 'white', fontWeight: 'bold', fontSize: '12px' }}>TWINT</span>
                </div>
                <span className="text-white text-sm">Twint</span>
              </div>
              <button
                type="button"
                onClick={() => setConcept({ ...concept, paymentTwint: !concept.paymentTwint })}
                className={`relative w-12 h-6 rounded-full transition-all duration-300 ${concept.paymentTwint ? 'bg-pink-500' : 'bg-gray-600'}`}
                data-testid="toggle-twint"
              >
                <span className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all duration-300 ${concept.paymentTwint ? 'left-7' : 'left-1'}`} />
              </button>
            </div>
            
            {/* Toggle PayPal */}
            <div className="flex items-center justify-between p-3 rounded-lg" style={{ background: 'rgba(139, 92, 246, 0.1)' }}>
              <div className="flex items-center gap-3">
                <img src="https://upload.wikimedia.org/wikipedia/commons/b/b5/PayPal.svg" alt="PayPal" style={{ height: '18px' }} onError={(e) => { e.target.src = ''; e.target.alt = 'PayPal'; }} />
                <span className="text-white text-sm">PayPal</span>
              </div>
              <button
                type="button"
                onClick={() => setConcept({ ...concept, paymentPaypal: !concept.paymentPaypal })}
                className={`relative w-12 h-6 rounded-full transition-all duration-300 ${concept.paymentPaypal ? 'bg-pink-500' : 'bg-gray-600'}`}
                data-testid="toggle-paypal"
              >
                <span className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all duration-300 ${concept.paymentPaypal ? 'left-7' : 'left-1'}`} />
              </button>
            </div>
            
            {/* Toggle Carte de Crédit */}
            <div className="flex items-center justify-between p-3 rounded-lg" style={{ background: 'rgba(139, 92, 246, 0.1)' }}>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1">
                  <img src="https://upload.wikimedia.org/wikipedia/commons/5/5e/Visa_Inc._logo.svg" alt="Visa" style={{ height: '14px' }} onError={(e) => { e.target.style.display = 'none'; }} />
                  <img src="https://upload.wikimedia.org/wikipedia/commons/2/2a/Mastercard-logo.svg" alt="Mastercard" style={{ height: '16px' }} onError={(e) => { e.target.style.display = 'none'; }} />
                </div>
                <span className="text-white text-sm">Carte de Crédit</span>
              </div>
              <button
                type="button"
                onClick={() => setConcept({ ...concept, paymentCreditCard: !concept.paymentCreditCard })}
                className={`relative w-12 h-6 rounded-full transition-all duration-300 ${concept.paymentCreditCard ? 'bg-pink-500' : 'bg-gray-600'}`}
                data-testid="toggle-creditcard"
              >
                <span className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all duration-300 ${concept.paymentCreditCard ? 'left-7' : 'left-1'}`} />
              </button>
            </div>
          </div>
        </div>

        {/* Affiche Événement */}
        <div className="border-t border-purple-500/30 pt-6">
          <h3 className="text-white text-sm font-semibold mb-4">🎉 Affiche Événement (Popup d'accueil)</h3>
          <p className="text-xs mb-4" style={{ color: 'rgba(255,255,255,0.4)' }}>
            Affichez une image ou vidéo en popup dès l'arrivée des visiteurs.
          </p>
          
          <div className="flex items-center justify-between p-3 rounded-lg mb-4" style={{ background: 'rgba(139, 92, 246, 0.1)' }}>
            <div className="flex items-center gap-3">
              <span className="text-2xl">📢</span>
              <span className="text-white text-sm">Activer l'affiche événement</span>
            </div>
            <button
              type="button"
              onClick={() => setConcept({ ...concept, eventPosterEnabled: !concept.eventPosterEnabled })}
              className={`relative w-12 h-6 rounded-full transition-all duration-300 ${concept.eventPosterEnabled ? 'bg-pink-500' : 'bg-gray-600'}`}
              data-testid="toggle-event-poster"
            >
              <span className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all duration-300 ${concept.eventPosterEnabled ? 'left-7' : 'left-1'}`} />
            </button>
          </div>
          
          {concept.eventPosterEnabled && (
            <div className="space-y-3">
              <div>
                <label className="block mb-1 text-white text-xs opacity-70">URL de l'image ou vidéo</label>
                <input 
                  type="url" 
                  value={concept.eventPosterMediaUrl || ''} 
                  onChange={(e) => setConcept({ ...concept, eventPosterMediaUrl: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
                  placeholder="https://... (image ou vidéo YouTube/Vimeo)"
                  data-testid="event-poster-url"
                />
              </div>
              
              {concept.eventPosterMediaUrl && (
                <div className="mt-3">
                  <label className="block mb-2 text-white text-xs opacity-70">Aperçu :</label>
                  <div className="rounded-lg overflow-hidden border border-purple-500/30" style={{ maxWidth: '300px' }}>
                    {concept.eventPosterMediaUrl.includes('youtube.com') || concept.eventPosterMediaUrl.includes('youtu.be') ? (
                      <div className="aspect-video">
                        <iframe 
                          src={`https://www.youtube.com/embed/${concept.eventPosterMediaUrl.includes('youtu.be') 
                            ? concept.eventPosterMediaUrl.split('/').pop() 
                            : new URLSearchParams(new URL(concept.eventPosterMediaUrl).search).get('v')}`}
                          className="w-full h-full"
                          frameBorder="0"
                          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                          allowFullScreen
                          title="Event poster preview"
                        />
                      </div>
                    ) : concept.eventPosterMediaUrl.includes('vimeo.com') ? (
                      <div className="aspect-video">
                        <iframe 
                          src={`https://player.vimeo.com/video/${concept.eventPosterMediaUrl.split('/').pop()}`}
                          className="w-full h-full"
                          frameBorder="0"
                          allow="autoplay; fullscreen; picture-in-picture"
                          allowFullScreen
                          title="Event poster preview"
                        />
                      </div>
                    ) : (
                      <img 
                        src={concept.eventPosterMediaUrl} 
                        alt="Aperçu affiche événement" 
                        className="w-full"
                        onError={(e) => { e.target.src = ''; e.target.alt = 'Image non valide'; }}
                      />
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Indicateur auto-save */}
        <div className="p-3 rounded-lg" style={{ background: 'rgba(34, 197, 94, 0.1)', border: '1px solid rgba(34, 197, 94, 0.2)' }}>
          <p className="text-green-400 text-sm flex items-center gap-2">
            <span>✓</span> Sauvegarde automatique activée - Vos modifications sont enregistrées instantanément
          </p>
        </div>
      </div>
    </div>
  );
};

export default ConceptEditor;

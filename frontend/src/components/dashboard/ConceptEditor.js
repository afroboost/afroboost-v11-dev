/**
 * ConceptEditor Component v36 — HUB centralisé avec sections filtrables
 * Éditeur de concept/personnalisation - Extrait de CoachDashboard.js
 *
 * Props:
 *   section: 'video-hero' | 'audio' | 'settings' | 'all' (default: 'all')
 *   - 'video-hero': Affiche les 3 slots média héro + Master Control Vidéos
 *   - 'audio': Affiche le Master Control Audio
 *   - 'settings': Affiche couleurs, paramètres généraux, liens, logos paiement, affiche événement
 *   - 'all': Affiche tout (rétro-compatible)
 */
import React, { useState, useEffect } from 'react';
import { LandingSectionSelector } from '../SearchBar';

const ConceptEditor = ({
  concept,
  setConcept,
  conceptSaveStatus,
  saveConcept,
  API,
  t,
  isSuperAdmin = false,
  coachEmail = '',
  courses = [],
  setCourses,
  section = 'all'
}) => {
  const [aiLegalLoading, setAiLegalLoading] = React.useState(false);
  const [uploadingVideo, setUploadingVideo] = React.useState(null); // slot index being uploaded

  // v46: State pour pistes audio autonomes (collection audio_tracks)
  const [masterAudioTracks, setMasterAudioTracks] = useState([]);
  useEffect(() => {
    if (section !== 'audio' && section !== 'all') return;
    if (!isSuperAdmin || !coachEmail || !API) return;
    const loadMasterAudio = async () => {
      try {
        const res = await fetch(`${API}/audio-tracks`, { headers: { 'X-User-Email': coachEmail } });
        if (res.ok) {
          const data = await res.json();
          setMasterAudioTracks(data.tracks || []);
        }
      } catch (e) { console.warn('[ConceptEditor] Audio tracks load failed:', e.message); }
    };
    loadMasterAudio();
  }, [section, isSuperAdmin, coachEmail, API]);

  // Helper: get heroVideos array (with migration from legacy heroImageUrl)
  const getHeroVideos = () => {
    if (concept.heroVideos && concept.heroVideos.length > 0) return concept.heroVideos;
    if (concept.heroImageUrl) return [{ url: concept.heroImageUrl, type: 'youtube', title: '' }];
    return [];
  };

  const updateHeroVideo = (index, updates) => {
    // updates = { url: '...', type: '...' } — on merge tout en un seul setConcept
    const videos = [...getHeroVideos()];
    if (videos[index]) {
      videos[index] = { ...videos[index], ...updates };
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

  // v32: Déplacer un média vers la gauche ou la droite
  const moveHeroVideo = (index, direction) => {
    const videos = [...getHeroVideos()];
    const newIndex = index + direction;
    if (newIndex < 0 || newIndex >= videos.length) return;
    // Swap
    [videos[index], videos[newIndex]] = [videos[newIndex], videos[index]];
    setConcept({ ...concept, heroVideos: videos, heroImageUrl: videos[0]?.url || '' });
  };

  const handleMediaUpload = async (file, slotIndex) => {
    if (!file) return;
    // Détecter le type automatiquement
    const isImage = file.type.startsWith('image/');
    const isVideo = file.type.startsWith('video/');
    if (!isImage && !isVideo) {
      alert('Format non supporté. Utilisez MP4, MOV, WEBM, JPG, PNG ou WEBP.');
      return;
    }
    // Vérifier la taille (Vercel limite à 4.5MB par requête)
    const maxMB = 4;
    if (file.size > maxMB * 1024 * 1024) {
      alert(`Fichier trop volumineux (${(file.size / 1024 / 1024).toFixed(1)}MB). Maximum: ${maxMB}MB.\n\nPour les vidéos, utilisez un lien YouTube ou Vimeo.\nPour les images, réduisez la taille avant d'uploader.`);
      return;
    }
    setUploadingVideo(slotIndex);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('asset_type', isImage ? 'image' : 'video');
      const res = await fetch(`${API}/coach/upload-asset`, {
        method: 'POST',
        headers: { 'X-User-Email': coachEmail },
        body: formData
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Erreur serveur (${res.status})`);
      }
      const data = await res.json();
      if (data.url) {
        const videos = [...getHeroVideos()];
        const mediaType = isImage ? 'image' : 'upload';
        videos[slotIndex] = { url: data.url, type: mediaType, title: file.name.replace(/\.[^.]+$/, '') };
        setConcept({ ...concept, heroVideos: videos, heroImageUrl: videos[0]?.url || '' });
      }
    } catch (err) {
      console.error('Erreur upload:', err);
      alert(`Erreur: ${err.message}`);
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
  // v37.2: Déterminer quelles sections afficher
  const showVideoHero = section === 'all' || section === 'video-hero';
  const showAudio = section === 'all' || section === 'audio';
  const showSettings = section === 'all' || section === 'settings';
  const showVitrine = section === 'all' || section === 'settings' || section === 'vitrine';
  const showBoutique = section === 'all' || section === 'settings' || section === 'boutique';

  // v37.2: Titres dynamiques par section
  const sectionTitle = section === 'video-hero' ? '🎬 Vidéo Hero'
    : section === 'audio' ? '🎧 Audio'
    : section === 'settings' ? '⚙️ Paramètres'
    : section === 'vitrine' ? '🖼️ Ma Vitrine'
    : section === 'boutique' ? '💳 Boutique & Paiements'
    : t('conceptVisual');

  return (
    <div className="card-gradient rounded-xl p-6">
      {/* Indicateur de sauvegarde automatique */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-semibold text-white" style={{ fontSize: '20px' }}>{sectionTitle}</h2>
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
        {/* PERSONNALISATION DES COULEURS — v37.2: section vitrine */}
        {showVitrine && (<div className="border border-purple-500/30 rounded-lg p-4 bg-purple-900/10">
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
        </div>)}

        {/* v37.2: PARAMÈTRES GÉNÉRAUX (sans Hero vidéos) — section vitrine */}
        {showVitrine && (<div className="border border-purple-500/30 rounded-lg p-4 bg-purple-900/10">
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
        </div>)}

        {/* v36: VIDÉOS HÉRO (3 max) — section video-hero — extrait du bloc Paramètres */}
        {showVideoHero && (<div className="border border-purple-500/30 rounded-lg p-4 bg-purple-900/10">
          <h3 className="text-purple-400 font-semibold mb-4">🎬 Médias Héro — vidéos ou images (max 3)</h3>
          {/* v18: Multi-Vidéos Héro (3 max) */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <label className="text-white text-xs opacity-70">🎬 Médias Héro — vidéos ou images (max 3)</label>
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
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ color: '#D91CD2', fontSize: '12px', fontWeight: 600 }}>Vidéo {idx + 1}</span>
                    {/* v32: Boutons de positionnement manuel */}
                    {getHeroVideos().length > 1 && (
                      <div style={{ display: 'flex', gap: '4px' }}>
                        <button
                          type="button"
                          onClick={() => moveHeroVideo(idx, -1)}
                          disabled={idx === 0}
                          style={{
                            background: idx === 0 ? 'rgba(255,255,255,0.05)' : 'rgba(217,28,210,0.15)',
                            border: `1px solid ${idx === 0 ? 'rgba(255,255,255,0.1)' : 'rgba(217,28,210,0.4)'}`,
                            color: idx === 0 ? 'rgba(255,255,255,0.2)' : '#D91CD2',
                            fontSize: '13px', padding: '1px 8px', borderRadius: '6px',
                            cursor: idx === 0 ? 'not-allowed' : 'pointer', fontWeight: 700,
                            transition: 'all 0.2s ease'
                          }}
                          title="Déplacer vers la gauche"
                        >◀</button>
                        <button
                          type="button"
                          onClick={() => moveHeroVideo(idx, 1)}
                          disabled={idx === getHeroVideos().length - 1}
                          style={{
                            background: idx === getHeroVideos().length - 1 ? 'rgba(255,255,255,0.05)' : 'rgba(217,28,210,0.15)',
                            border: `1px solid ${idx === getHeroVideos().length - 1 ? 'rgba(255,255,255,0.1)' : 'rgba(217,28,210,0.4)'}`,
                            color: idx === getHeroVideos().length - 1 ? 'rgba(255,255,255,0.2)' : '#D91CD2',
                            fontSize: '13px', padding: '1px 8px', borderRadius: '6px',
                            cursor: idx === getHeroVideos().length - 1 ? 'not-allowed' : 'pointer', fontWeight: 700,
                            transition: 'all 0.2s ease'
                          }}
                          title="Déplacer vers la droite"
                        >▶</button>
                      </div>
                    )}
                  </div>
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
                    const type = isYT ? 'youtube' : isVimeo ? 'vimeo' : (video.type || 'link');
                    updateHeroVideo(idx, { url, type });
                  }}
                  className="w-full px-3 py-2 rounded-lg neon-input text-sm"
                  placeholder="Lien YouTube ou Vimeo (ex: https://youtu.be/...)"
                  style={{ marginBottom: '6px' }}
                />
                <div style={{ marginTop: '4px', display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                  {/* Upload image (tous) */}
                  <label
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: '6px', cursor: uploadingVideo !== null ? 'wait' : 'pointer',
                      background: 'rgba(34,197,94,0.12)', border: '1px solid rgba(34,197,94,0.3)',
                      padding: '4px 10px', borderRadius: '8px', fontSize: '11px', color: '#22c55e',
                      opacity: uploadingVideo !== null ? 0.5 : 1
                    }}
                  >
                    {uploadingVideo === idx ? '⏳ Upload...' : '🖼️ Upload image (JPG/PNG)'}
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
                      style={{ display: 'none' }}
                      onChange={(e) => { if (e.target.files[0]) handleMediaUpload(e.target.files[0], idx); }}
                      disabled={uploadingVideo !== null}
                    />
                  </label>
                  {/* Upload vidéo (admin only) */}
                  {isSuperAdmin && (
                    <label
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: '6px', cursor: uploadingVideo !== null ? 'wait' : 'pointer',
                        background: 'rgba(139,92,246,0.15)', border: '1px solid rgba(139,92,246,0.3)',
                        padding: '4px 10px', borderRadius: '8px', fontSize: '11px', color: '#a78bfa',
                        opacity: uploadingVideo !== null ? 0.5 : 1
                      }}
                    >
                      {uploadingVideo === idx ? '⏳ Upload...' : '📁 Upload vidéo (MP4/MOV)'}
                      <input
                        type="file"
                        accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm"
                        style={{ display: 'none' }}
                        onChange={(e) => { if (e.target.files[0]) handleMediaUpload(e.target.files[0], idx); }}
                        disabled={uploadingVideo !== null}
                      />
                    </label>
                  )}
                  <span style={{ fontSize: '10px', color: 'rgba(255,255,255,0.3)' }}>
                    Max 4MB — pour les vidéos, utilisez YouTube/Vimeo
                  </span>
                </div>
                {/* v34: Champs Vidéo Premium — Prix, Description, Miniature */}
                <div style={{
                  marginTop: '8px', padding: '10px', borderRadius: '8px',
                  background: 'rgba(217,28,210,0.05)', border: '1px solid rgba(217,28,210,0.15)'
                }}>
                  <p style={{ color: '#D91CD2', fontSize: '11px', fontWeight: 600, marginBottom: '6px' }}>💎 Options Vidéo Premium</p>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '6px' }}>
                    <div style={{ flex: '0 0 100px' }}>
                      <label style={{ display: 'block', color: 'rgba(255,255,255,0.5)', fontSize: '10px', marginBottom: '2px' }}>Prix (CHF)</label>
                      <input
                        type="number"
                        min="0"
                        step="0.5"
                        value={video.price || ''}
                        onChange={(e) => updateHeroVideo(idx, { price: parseFloat(e.target.value) || 0 })}
                        className="w-full px-2 py-1.5 rounded-lg neon-input text-sm"
                        placeholder="0"
                        style={{ maxWidth: '100px' }}
                      />
                    </div>
                    <div style={{ flex: '1', minWidth: '150px' }}>
                      <label style={{ display: 'block', color: 'rgba(255,255,255,0.5)', fontSize: '10px', marginBottom: '2px' }}>Description</label>
                      <input
                        type="text"
                        value={video.description || ''}
                        onChange={(e) => updateHeroVideo(idx, { description: e.target.value })}
                        className="w-full px-2 py-1.5 rounded-lg neon-input text-sm"
                        placeholder="ex: Masterclass Cardio"
                      />
                    </div>
                  </div>
                  <div>
                    <label style={{ display: 'block', color: 'rgba(255,255,255,0.5)', fontSize: '10px', marginBottom: '2px' }}>Miniature personnalisée (URL)</label>
                    <input
                      type="url"
                      value={video.thumbnail || ''}
                      onChange={(e) => updateHeroVideo(idx, { thumbnail: e.target.value })}
                      className="w-full px-2 py-1.5 rounded-lg neon-input text-sm"
                      placeholder="https://... (optionnel)"
                    />
                  </div>
                  {/* v34: Toggle visibilité */}
                  <div style={{ marginTop: '6px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={video.is_visible !== false}
                        onChange={(e) => updateHeroVideo(idx, { is_visible: e.target.checked })}
                        style={{ accentColor: '#D91CD2' }}
                      />
                      <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px' }}>
                        {video.is_visible !== false ? '👁️ Visible' : '🚫 Masquée'}
                      </span>
                    </label>
                    {(video.price || 0) > 0 && (
                      <span style={{ fontSize: '10px', color: '#D91CD2', fontWeight: 600 }}>
                        ⏱️ Preview 30s activée
                      </span>
                    )}
                  </div>
                </div>

                {/* Aperçu YouTube/Vimeo */}
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
                        title={`Aperçu vidéo ${idx + 1}`}
                      />
                    </div>
                  </div>
                )}
                {/* Aperçu fichier uploadé (vidéo MP4/MOV) */}
                {video.url && video.url.startsWith('/api/files/') && video.type !== 'image' && (
                  <div style={{ marginTop: '6px', borderRadius: '8px', overflow: 'hidden', maxWidth: '240px' }}>
                    <video
                      src={video.url}
                      controls
                      muted
                      style={{ width: '100%', borderRadius: '8px', background: '#000' }}
                    />
                    <p style={{ fontSize: '10px', color: 'rgba(255,255,255,0.3)', marginTop: '2px' }}>
                      {video.title || 'Vidéo uploadée'}
                    </p>
                  </div>
                )}
                {/* Aperçu fichier uploadé (image) */}
                {video.url && (video.type === 'image' || video.url.match(/\.(jpg|jpeg|png|webp|gif)$/i)) && (
                  <div style={{ marginTop: '6px', borderRadius: '8px', overflow: 'hidden', maxWidth: '240px' }}>
                    <img
                      src={video.url}
                      alt={video.title || 'Image héro'}
                      style={{ width: '100%', borderRadius: '8px', objectFit: 'cover' }}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>)}

        {/* v37.2: BRANDING & IDENTITÉ (Logo, Favicon) — section vitrine */}
        {showVitrine && (<div className="border border-purple-500/30 rounded-lg p-4 bg-purple-900/10">
          <h3 className="text-purple-400 font-semibold mb-4">🏷️ Branding & Identité</h3>
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
        </div>)}

        {/* v37.2: CGV & GOOGLE REVIEWS — section boutique */}
        {showBoutique && (<div className="border border-purple-500/30 rounded-lg p-4 bg-purple-900/10">
          <h3 className="text-purple-400 font-semibold mb-4">📋 Conditions & Avis</h3>
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
    {/* V93.6: Conditions générales partenaires */}
    <div className="mb-4">
      <label className="text-white text-xs opacity-70 mb-1 block">Conditions Générales Partenaires</label>
      <textarea
        value={concept.termsTextPartners || ''}
        onChange={(e) => setConcept({ ...concept, termsTextPartners: e.target.value })}
        className="w-full px-3 py-2 rounded-lg neon-input text-sm"
        rows={4}
        placeholder="Conditions générales pour les partenaires/coachs..."
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
                <a href={concept.googleReviewsUrl} target="_blank" rel="noopener noreferrer" className="text-xs text-pink-400 hover:text-pink-300 underline">Tester le lien</a>
              </div>
            )}
          </div>
        </div>)}

        {/* Section d'atterrissage — v37.2: section boutique */}
        {showBoutique && (<div className="border border-purple-500/30 rounded-lg p-4 bg-purple-900/10">
          <LandingSectionSelector
            value={concept.defaultLandingSection || 'sessions'}
            onChange={(value) => setConcept({ ...concept, defaultLandingSection: value })}
          />
        </div>)}

        {/* V119: Ordre des sections vitrine — sessions-first ou offers-first */}
        {showVitrine && (<div className="border border-purple-500/30 rounded-lg p-4 bg-purple-900/10">
          <h3 className="text-white text-sm font-semibold mb-3">📐 Ordre des sections vitrine</h3>
          <p className="text-white/50 text-xs mb-3">Choisissez quel bloc apparaît en premier sur la page publique</p>
          <div className="flex gap-3">
            <button
              onClick={() => setConcept({ ...concept, vitrineSectionOrder: 'sessions-first' })}
              className="flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-all"
              style={{
                background: (concept.vitrineSectionOrder || 'sessions-first') === 'sessions-first'
                  ? 'linear-gradient(135deg, rgba(217, 28, 210, 0.3), rgba(139, 92, 246, 0.3))'
                  : 'rgba(255, 255, 255, 0.06)',
                border: (concept.vitrineSectionOrder || 'sessions-first') === 'sessions-first'
                  ? '1px solid rgba(217, 28, 210, 0.5)'
                  : '1px solid rgba(255, 255, 255, 0.1)',
                color: (concept.vitrineSectionOrder || 'sessions-first') === 'sessions-first' ? '#fff' : 'rgba(255, 255, 255, 0.6)'
              }}
            >
              📅 Sessions d'abord
            </button>
            <button
              onClick={() => setConcept({ ...concept, vitrineSectionOrder: 'offers-first' })}
              className="flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-all"
              style={{
                background: concept.vitrineSectionOrder === 'offers-first'
                  ? 'linear-gradient(135deg, rgba(217, 28, 210, 0.3), rgba(139, 92, 246, 0.3))'
                  : 'rgba(255, 255, 255, 0.06)',
                border: concept.vitrineSectionOrder === 'offers-first'
                  ? '1px solid rgba(217, 28, 210, 0.5)'
                  : '1px solid rgba(255, 255, 255, 0.1)',
                color: concept.vitrineSectionOrder === 'offers-first' ? '#fff' : 'rgba(255, 255, 255, 0.6)'
              }}
            >
              🎁 Offres d'abord
            </button>
          </div>
        </div>)}

        {/* Liens Externes — v37.2: section vitrine */}
        {showVitrine && (<div className="border border-purple-500/30 rounded-lg p-4 bg-purple-900/10">
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
        </div>)}

        {/* Logos de paiement — v37.2: section boutique */}
        {showBoutique && (<div className="border border-purple-500/30 rounded-lg p-4 bg-purple-900/10">
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
        </div>)}

        {/* Affiche Événement — v37.2: section vitrine */}
        {showVitrine && (<div className="border border-purple-500/30 rounded-lg p-4 bg-purple-900/10">
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
        </div>)}

        {/* v34: MASTER CONTROL SUPER ADMIN — Gestion centralisée des vidéos — v36: section video-hero */}
        {showVideoHero && isSuperAdmin && getHeroVideos().length > 0 && (
          <div className="border border-red-500/30 rounded-lg p-4 bg-red-900/10">
            <h3 className="text-red-400 font-semibold mb-4">🛡️ Master Control — Gestion Vidéos</h3>
            <p className="text-white/40 text-xs mb-3">Actions admin sur toutes les vidéos héro configurées.</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {getHeroVideos().map((video, idx) => (
                <div key={idx} style={{
                  display: 'flex', flexDirection: 'column', gap: '8px',
                  padding: '10px 12px', borderRadius: '8px',
                  background: video.is_visible === false ? 'rgba(239,68,68,0.08)' : 'rgba(255,255,255,0.04)',
                  border: `1px solid ${video.is_visible === false ? 'rgba(239,68,68,0.2)' : 'rgba(255,255,255,0.08)'}`
                }}>
                  {/* Titre + infos */}
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                      <span style={{ color: '#D91CD2', fontSize: '12px', fontWeight: 700 }}>#{idx + 1}</span>
                      <span style={{ color: '#fff', fontSize: '12px', fontWeight: 500 }}>{video.title || video.description || 'Sans titre'}</span>
                      {(video.price || 0) > 0 && (
                        <span style={{ color: '#22c55e', fontSize: '11px', fontWeight: 600 }}>{video.price} CHF</span>
                      )}
                      {video.is_visible === false && (
                        <span style={{ color: '#ef4444', fontSize: '10px' }}>🚫 MASQUÉE</span>
                      )}
                    </div>
                    <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '10px', wordBreak: 'break-all', display: 'block', marginTop: '4px' }}>
                      {video.url?.substring(0, 50)}{video.url?.length > 50 ? '...' : ''}
                    </span>
                  </div>
                  {/* Boutons actions */}
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {/* Toggle invisible */}
                    <button
                      type="button"
                      onClick={() => updateHeroVideo(idx, { is_visible: video.is_visible === false ? true : false })}
                      style={{
                        background: video.is_visible === false ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                        border: `1px solid ${video.is_visible === false ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                        color: video.is_visible === false ? '#22c55e' : '#ef4444',
                        fontSize: '11px', padding: '5px 10px', borderRadius: '6px', cursor: 'pointer',
                        display: 'flex', alignItems: 'center', gap: '4px'
                      }}
                      title={video.is_visible === false ? 'Rendre visible' : 'Masquer'}
                    >
                      {video.is_visible === false ? '👁️ Afficher' : '🚫 Masquer'}
                    </button>
                    {/* Copier le lien */}
                    <button
                      type="button"
                      onClick={() => {
                        const baseUrl = window.location.origin;
                        navigator.clipboard.writeText(video.url?.startsWith('/api/') ? `${baseUrl}${video.url}` : (video.url || ''));
                        alert('Lien copié !');
                      }}
                      style={{
                        background: 'rgba(139,92,246,0.15)', border: '1px solid rgba(139,92,246,0.3)',
                        color: '#a78bfa', fontSize: '11px', padding: '5px 10px', borderRadius: '6px', cursor: 'pointer',
                        display: 'flex', alignItems: 'center', gap: '4px'
                      }}
                      title="Copier le lien direct"
                    >
                      🔗 Copier
                    </button>
                    {/* Supprimer */}
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm(`Supprimer la vidéo #${idx + 1} "${video.title || 'Sans titre'}" ?`)) {
                          removeHeroVideo(idx);
                        }
                      }}
                      style={{
                        background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)',
                        color: '#ef4444', fontSize: '11px', padding: '5px 10px', borderRadius: '6px', cursor: 'pointer',
                        display: 'flex', alignItems: 'center', gap: '4px'
                      }}
                      title="Supprimer"
                    >
                      🗑️ Suppr.
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* v46: MASTER CONTROL SUPER ADMIN — Gestion centralisée des audios — SOURCE: collection audio_tracks */}
        {showAudio && isSuperAdmin && masterAudioTracks.length > 0 && (() => {
          const toggleAudioVisible = async (trackId, currentVisible) => {
            try {
              const res = await fetch(`${API}/audio-tracks/${trackId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'X-User-Email': coachEmail },
                body: JSON.stringify({ visible: !currentVisible })
              });
              if (res.ok) {
                setMasterAudioTracks(prev => prev.map(t => t.id === trackId ? { ...t, visible: !currentVisible } : t));
              }
            } catch (e) { console.error('[MasterControl] Toggle visible error:', e); }
          };

          const deleteAudioTrack = async (trackId, title) => {
            if (!window.confirm(`Supprimer l'audio "${title}" ?`)) return;
            try {
              const res = await fetch(`${API}/audio-tracks/${trackId}`, {
                method: 'DELETE',
                headers: { 'X-User-Email': coachEmail }
              });
              if (res.ok) {
                setMasterAudioTracks(prev => prev.filter(t => t.id !== trackId));
              }
            } catch (e) { console.error('[MasterControl] Delete error:', e); }
          };

          return (
            <div className="border border-orange-500/30 rounded-lg p-4 bg-orange-900/10" style={{ marginBottom: '16px' }}>
              <h3 className="text-orange-400 font-semibold mb-4">🎧 Master Control — Gestion Audios</h3>
              <p className="text-white/40 text-xs mb-3">Actions admin sur tous les audios autonomes. ({masterAudioTracks.length} piste{masterAudioTracks.length > 1 ? 's' : ''})</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {masterAudioTracks.map((track, idx) => (
                  <div key={track.id || idx} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '8px 12px', borderRadius: '8px',
                    background: track.visible === false ? 'rgba(239,68,68,0.08)' : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${track.visible === false ? 'rgba(239,68,68,0.2)' : 'rgba(255,255,255,0.08)'}`
                  }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '16px' }}>{track.cover_url ? '🖼️' : '🎵'}</span>
                        <span style={{ color: '#fff', fontSize: '12px', fontWeight: 600 }}>{track.title || 'Sans titre'}</span>
                        {(track.price || 0) > 0 ? (
                          <span style={{ color: '#22c55e', fontSize: '11px', fontWeight: 600 }}>💎 {track.price} CHF</span>
                        ) : (
                          <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '10px' }}>Gratuit</span>
                        )}
                        {track.visible === false && (
                          <span style={{ color: '#ef4444', fontSize: '10px' }}>🚫 MASQUÉ</span>
                        )}
                      </div>
                      <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '10px' }}>
                        Collection audio_tracks • order: {track.order}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: '4px', marginLeft: '8px' }}>
                      {/* Toggle visible */}
                      <button
                        type="button"
                        onClick={() => toggleAudioVisible(track.id, track.visible !== false)}
                        style={{
                          background: track.visible === false ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                          border: `1px solid ${track.visible === false ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                          color: track.visible === false ? '#22c55e' : '#ef4444',
                          fontSize: '10px', padding: '3px 8px', borderRadius: '6px', cursor: 'pointer'
                        }}
                        title={track.visible === false ? 'Rendre visible' : 'Masquer'}
                      >
                        {track.visible === false ? '👁️' : '🚫'}
                      </button>
                      {/* Copier le lien */}
                      <button
                        type="button"
                        onClick={() => {
                          const baseUrl = window.location.origin;
                          const url = track.url?.startsWith('/api/') ? `${baseUrl}${track.url}` : (track.url || '');
                          navigator.clipboard.writeText(url);
                          alert('Lien audio copié !');
                        }}
                        style={{
                          background: 'rgba(139,92,246,0.15)', border: '1px solid rgba(139,92,246,0.3)',
                          color: '#a78bfa', fontSize: '10px', padding: '3px 8px', borderRadius: '6px', cursor: 'pointer'
                        }}
                        title="Copier le lien"
                      >🔗</button>
                      {/* Supprimer */}
                      <button
                        type="button"
                        onClick={() => deleteAudioTrack(track.id, track.title || 'Sans titre')}
                        style={{
                          background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)',
                          color: '#ef4444', fontSize: '10px', padding: '3px 8px', borderRadius: '6px', cursor: 'pointer'
                        }}
                        title="Supprimer"
                      >🗑️</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })()}

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

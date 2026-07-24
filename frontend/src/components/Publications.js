// V261 — Publications des abonnes (image / video 9:16, duree de vie 48 h)
//
// Module SEPARE, et non un ajout a App.js : `SubscriberSpace` a besoin de
// `PublishModal`, et App.js importe deja `SubscriberSpace`. Les loger dans
// App.js creerait une dependance circulaire — le genre de cycle qui rend un
// composant `undefined` a l'execution selon l'ordre d'evaluation des modules.

import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const API = `${BACKEND_URL}/api`;

export const PublicationsCarousel = ({ publications }) => {
  if (!publications || publications.length === 0) return null;
  return (
    <div className="mb-8 fade-in-section" data-testid="publications-carousel">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" style={{ stroke: 'var(--primary-color, #D91CD2)', flexShrink: 0 }} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
          <path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
        <span style={{ color: '#fff', fontSize: '18px', fontWeight: 600 }}>
          Publications ({publications.length})
        </span>
      </div>
      {/* `hide-scrollbar` existe deja dans App.css — pas de nouvelle regle CSS
          a inventer pour masquer la barre de defilement. */}
      <div
        className="hide-scrollbar"
        style={{
          display: 'flex', overflowX: 'auto', gap: 10, paddingBottom: 4,
          scrollSnapType: 'x mandatory', WebkitOverflowScrolling: 'touch'
        }}
      >
        {publications.map(pub => (
          <div
            key={pub.id}
            style={{
              flexShrink: 0, width: 160, height: 284, borderRadius: 12,
              overflow: 'hidden', position: 'relative',
              scrollSnapAlign: 'start', background: '#000'
            }}
          >
            {pub.media_type === 'video' ? (
              // `muted` est INDISPENSABLE avec `autoPlay` : sans lui, iOS et
              // Chrome refusent la lecture automatique et la vignette reste noire.
              <video
                src={pub.media_url}
                playsInline muted loop autoPlay
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
            ) : (
              <img
                src={pub.media_url}
                alt={`Publication de ${pub.subscriber_name || 'un abonné'}`}
                loading="lazy"
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
            )}
            <div style={{
              position: 'absolute', bottom: 0, left: 0, right: 0,
              background: 'linear-gradient(transparent, rgba(0,0,0,0.85))',
              padding: '20px 8px 8px'
            }}>
              <p style={{ color: '#fff', fontSize: '0.7rem', fontWeight: 600, margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {pub.subscriber_name}
              </p>
              <p style={{ color: '#bbb', fontSize: '0.6rem', margin: '2px 0 0', display: 'flex', alignItems: 'center', gap: 3 }}>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
                  <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
                </svg>
                {pub.remaining_hours >= 1 ? Math.floor(pub.remaining_hours) + 'h' : '< 1h'}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// Modale de publication, ouverte depuis l'espace abonne.
// `subscriberCode` absent = mode COACH (V263) : le serveur identifie alors le
// coach par sa session authentifiee, jamais par une valeur envoyee d'ici.
export const PublishModal = ({ subscriberCode, onClose, onPublished }) => {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [mediaType, setMediaType] = useState('image');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);

  // L'URL d'objet est liberee au demontage ET a chaque remplacement : sans
  // cela, choisir cinq fichiers de suite laisse cinq blobs en memoire.
  useEffect(() => {
    return () => { if (preview) URL.revokeObjectURL(preview); };
  }, [preview]);

  const handleFileSelect = (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    setError('');
    if (preview) URL.revokeObjectURL(preview);
    setMediaType(f.type.startsWith('video/') ? 'video' : 'image');
    setFile(f);
    setPreview(URL.createObjectURL(f));
  };

  const clearFile = () => {
    if (preview) URL.revokeObjectURL(preview);
    setFile(null);
    setPreview(null);
  };

  const handleUploadAndPublish = async () => {
    if (!file || uploading) return;
    setUploading(true);
    setError('');
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('upload_preset', 'afroboost');
      formData.append('folder', 'publications');
      const endpoint = mediaType === 'video'
        ? 'https://api.cloudinary.com/v1_1/dtm0r7hwq/video/upload'
        : 'https://api.cloudinary.com/v1_1/dtm0r7hwq/image/upload';
      // PAS de `transformation` dans le formulaire : un preset UNSIGNED la
      // refuse (Cloudinary renvoie « Transformation parameter is not allowed
      // when using unsigned upload »). Le cadrage 9:16 est fait a l'affichage
      // par `objectFit: cover`, ce qui evite aussi de deteriorer l'original.
      const cloudRes = await axios.post(endpoint, formData);
      // V261b: `cloudinary_public_id` n'est PLUS envoye — le serveur le derive
      // lui-meme de l'URL. Il finissait en argument de `destroy()` : un client
      // pouvait y designer le media d'un autre et le faire effacer.
      // V263: sans code abonne, on n'envoie RIEN qui designe l'auteur — le
      // serveur le deduit de la session (JWT ou en-tete). Envoyer un
      // `coach_email` ici rouvrirait la falsification corrigee en V262.
      var payload = { media_url: cloudRes.data.secure_url, media_type: mediaType };
      if (subscriberCode) payload.subscriber_code = subscriberCode;
      await axios.post(`${API}/publications`, payload);
      setUploading(false);
      if (onPublished) onPublished();
      onClose();
    } catch (err) {
      setUploading(false);
      setError(
        err?.response?.data?.detail
        || err?.response?.data?.error?.message
        || "La publication a échoué. Réessayez."
      );
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 9998, background: 'rgba(0,0,0,0.9)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ background: '#1a1a2e', borderRadius: 16, padding: 24, maxWidth: 380, width: '100%', maxHeight: '92vh', overflowY: 'auto' }}
        data-testid="publish-modal"
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ color: '#fff', fontSize: '1rem', margin: 0 }}>Nouvelle publication</h3>
          <button onClick={onClose} aria-label="Fermer" style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#999', padding: 0 }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {!preview ? (
          <div
            onClick={() => fileInputRef.current && fileInputRef.current.click()}
            style={{
              width: '100%', aspectRatio: '9/16', maxHeight: 380, background: '#0a0a1a',
              borderRadius: 12, border: '2px dashed #333', display: 'flex',
              flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              cursor: 'pointer', gap: 12
            }}
            data-testid="publish-picker"
          >
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" style={{ stroke: 'var(--primary-color, #D91CD2)' }} strokeWidth="2" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            <p style={{ color: '#999', fontSize: '0.85rem', margin: 0 }}>Appuyez pour choisir</p>
            <p style={{ color: '#666', fontSize: '0.7rem', margin: 0 }}>Image ou vidéo (format 9:16)</p>
          </div>
        ) : (
          <div style={{ position: 'relative', width: '100%', borderRadius: 12, overflow: 'hidden', background: '#000' }}>
            {mediaType === 'video' ? (
              <video src={preview} controls playsInline style={{ width: '100%', maxHeight: 380, objectFit: 'contain', display: 'block' }} />
            ) : (
              <img src={preview} alt="Aperçu" style={{ width: '100%', maxHeight: 380, objectFit: 'contain', display: 'block' }} />
            )}
            <button
              onClick={clearFile}
              aria-label="Changer de média"
              style={{
                position: 'absolute', top: 8, right: 8, background: 'rgba(0,0,0,0.6)',
                border: 'none', borderRadius: '50%', width: 32, height: 32, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center'
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,video/*"
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />

        <p style={{ color: '#666', fontSize: '0.7rem', marginTop: 12, display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center' }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0 }}>
            <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
          </svg>
          Visible 48 h, puis supprimée automatiquement
        </p>

        {error && (
          <p style={{ color: '#f87171', fontSize: '0.8rem', textAlign: 'center', marginTop: 8 }}>{error}</p>
        )}

        {preview && (
          <button
            onClick={handleUploadAndPublish}
            disabled={uploading}
            style={{
              width: '100%', padding: '12px', borderRadius: 25,
              background: uploading ? '#666' : 'var(--primary-color, #D91CD2)',
              color: '#fff', border: 'none', cursor: uploading ? 'wait' : 'pointer',
              fontWeight: 700, fontSize: '0.95rem', marginTop: 12
            }}
            data-testid="publish-submit"
          >
            {uploading ? 'Publication en cours…' : 'Publier'}
          </button>
        )}
      </div>
    </div>
  );
};

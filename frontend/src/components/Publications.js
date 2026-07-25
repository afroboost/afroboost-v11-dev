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

// V268b — Fix C : plus de barre visuelle ni du mot « restantes ». Juste « 47h »,
// dans la couleur DYNAMIQUE du coach (var(--primary-color), pilotee par le
// concept, V259) — jamais une couleur fixe.
const V268Remaining = ({ remaining }) => {
  const h = Math.floor(remaining || 0);
  return (
    <span style={{ color: 'var(--primary-color, #D91CD2)', fontSize: '0.7rem', fontWeight: 600 }}>
      {h >= 1 ? h + 'h' : '< 1h'}
    </span>
  );
};

// V268 (F7) / V268b Fix B1 : bouton son SANS rond — juste l'icone SVG, avec un
// leger drop-shadow pour rester lisible sur n'importe quelle image.
// `onToggle` recoit l'evenement pour que l'appelant fasse l'action AUDIO
// directement dans le handler du clic (exigence des navigateurs mobiles).
const V268MuteButton = ({ muted, onToggle, size }) => (
  <button
    type="button"
    onClick={onToggle}
    aria-label={muted ? 'Activer le son' : 'Couper le son'}
    title={muted ? 'Activer le son' : 'Couper le son'}
    style={{
      background: 'transparent', border: 'none', padding: 4, cursor: 'pointer',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      filter: 'drop-shadow(0 0 2px rgba(0,0,0,0.7))'
    }}
  >
    {muted ? (
      <svg width={size || 20} height={size || 20} viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
        <line x1="23" y1="9" x2="17" y2="15" /><line x1="17" y1="9" x2="23" y2="15" />
      </svg>
    ) : (
      <svg width={size || 20} height={size || 20} viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
        <path d="M15.54 8.46a5 5 0 0 1 0 7.07" /><path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
      </svg>
    )}
  </button>
);

// V268b Fix B2 : coupe/active le son EN DIRECT dans le handler du clic. Les
// navigateurs mobiles bloquent le son s'il n'est pas active par un geste
// utilisateur synchrone — donc pas de setState-updater a effet de bord, pas de
// Promise : on touche `video.muted` / `.volume` tout de suite.
const v268ToggleSound = (videoRef, setMuted) => (e) => {
  if (e) e.stopPropagation();
  const video = videoRef.current;
  if (!video) return;
  video.muted = !video.muted;
  if (!video.muted) video.volume = 1.0;
  setMuted(video.muted);
};

// V268 (F5): légende avec « Lire plus » / « Voir moins » au-delà de 100 car.
const V268Caption = ({ caption, light }) => {
  const [open, setOpen] = useState(false);
  if (!caption) return null;
  const long = caption.length > 100;
  const shown = open || !long ? caption : caption.slice(0, 100) + '… ';
  return (
    <p style={{ color: light ? '#ddd' : '#ccc', fontSize: light ? '14px' : '0.62rem', margin: light ? '10px 0 0' : '4px 0 0', lineHeight: 1.4, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
      {shown}
      {long && (
        <span
          onClick={(e) => { e.stopPropagation(); setOpen(o => !o); }}
          style={{ color: 'var(--primary-color, #D91CD2)', cursor: 'pointer', fontWeight: 600 }}
        >
          {open ? ' Voir moins' : 'Lire plus'}
        </span>
      )}
    </p>
  );
};

// V268 (F2): plein écran d'une publication au clic.
const V268Lightbox = ({ pub, onClose }) => {
  const videoRef = useRef(null);
  // Les vidéos démarrent muettes (autoplay) même en lightbox — le son s'active
  // au bouton, comme Instagram.
  const [muted, setMuted] = useState(true);
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  const toggleMute = v268ToggleSound(videoRef, setMuted); // V268b Fix B2
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999, background: 'rgba(0,0,0,0.92)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16
      }}
      data-testid="publication-lightbox"
    >
      <button
        onClick={onClose}
        aria-label="Fermer"
        style={{
          position: 'absolute', top: 14, right: 14, zIndex: 2,
          width: 40, height: 40, borderRadius: '50%', background: 'rgba(0,0,0,0.6)',
          border: 'none', color: '#fff', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)'
        }}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
          <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ position: 'relative', maxWidth: 'min(92vw, 480px)', width: '100%', maxHeight: '92vh', display: 'flex', flexDirection: 'column' }}
      >
        <div style={{ position: 'relative', display: 'flex', justifyContent: 'center' }}>
          {pub.media_type === 'video' ? (
            <>
              <video
                ref={videoRef}
                src={pub.media_url}
                autoPlay loop playsInline muted={muted}
                style={{ display: 'block', maxWidth: '100%', maxHeight: '78vh', borderRadius: 12, background: '#000' }}
              />
              <div style={{ position: 'absolute', bottom: 12, right: 12 }}>
                <V268MuteButton muted={muted} onToggle={toggleMute} size={26} />
              </div>
            </>
          ) : (
            <img
              src={pub.media_url}
              alt={`Publication de ${pub.display_name || pub.subscriber_name || 'un abonné'}`}
              style={{ display: 'block', maxWidth: '100%', maxHeight: '78vh', borderRadius: 12, objectFit: 'contain', background: '#000' }}
            />
          )}
        </div>
        <div style={{ padding: '4px 4px 0' }}>
          {/* V268b: nom AFFICHE (display_name), repli sur l'ancien champ. */}
          <p style={{ color: '#fff', fontSize: 14, fontWeight: 700, margin: '10px 0 0' }}>{pub.display_name || pub.subscriber_name}</p>
          <V268Caption caption={pub.caption} light />
        </div>
      </div>
    </div>
  );
};

// V268: une carte du carrousel. Composant séparé pour porter l'état local
// (son de la vidéo) sans le partager entre cartes.
const V268PublicationCard = ({ pub, onOpen }) => {
  const videoRef = useRef(null);
  const [muted, setMuted] = useState(true);
  const toggleMute = v268ToggleSound(videoRef, setMuted); // V268b Fix B2
  return (
    <div style={{ flexShrink: 0, width: 160, scrollSnapAlign: 'start' }}>
      <div
        onClick={() => onOpen(pub)}
        style={{
          width: 160, height: 284, borderRadius: 12, overflow: 'hidden',
          position: 'relative', background: '#000', cursor: 'pointer'
        }}
        data-testid="publication-card"
      >
        {pub.media_type === 'video' ? (
          <>
            {/* `muted` requis avec `autoPlay` (iOS/Chrome). Le bouton son
                pilote `muted` via le ref. V268b Fix A : `display:block` evite
                l'espace sous une video/img `inline` qui faisait deborder. */}
            <video
              ref={videoRef}
              src={pub.media_url}
              poster={pub.thumbnail_url || undefined}
              playsInline muted={muted} loop autoPlay
              style={{ display: 'block', width: '100%', height: '100%', objectFit: 'cover' }}
            />
            <div style={{ position: 'absolute', bottom: 40, right: 6 }}>
              <V268MuteButton muted={muted} onToggle={toggleMute} size={18} />
            </div>
          </>
        ) : (
          <img
            src={pub.media_url}
            alt={`Publication de ${pub.display_name || pub.subscriber_name || 'un abonné'}`}
            loading="lazy"
            style={{ display: 'block', width: '100%', height: '100%', objectFit: 'cover' }}
          />
        )}
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0,
          background: 'linear-gradient(transparent, rgba(0,0,0,0.88))',
          padding: '22px 8px 8px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
            <p style={{ color: '#fff', fontSize: '0.7rem', fontWeight: 600, margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {pub.display_name || pub.subscriber_name}
            </p>
            {/* V268b Fix C : « 47h » seul, couleur dynamique du coach. */}
            <V268Remaining remaining={pub.remaining_hours} />
          </div>
        </div>
      </div>
      {/* V268 (F5): legende courte sous la carte ; le texte complet + Lire plus
          vit dans la lightbox, ou il y a la place. */}
      {pub.caption ? (
        <p
          onClick={() => onOpen(pub)}
          style={{ color: '#bbb', fontSize: '0.62rem', margin: '5px 2px 0', lineHeight: 1.3, cursor: 'pointer', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}
        >
          {pub.caption}
        </p>
      ) : null}
    </div>
  );
};

export const PublicationsCarousel = ({ publications }) => {
  // V268 (F2): publication ouverte en plein ecran, ou null.
  const [lightbox, setLightbox] = useState(null);
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
        {/* V268 (F4): plus de compteur « (N) » a cote du titre. */}
        <span style={{ color: '#fff', fontSize: '18px', fontWeight: 600 }}>Publications</span>
      </div>
      <div
        className="hide-scrollbar"
        style={{
          display: 'flex', overflowX: 'auto', gap: 10, paddingBottom: 4,
          alignItems: 'flex-start',
          scrollSnapType: 'x mandatory', WebkitOverflowScrolling: 'touch'
        }}
      >
        {publications.map(pub => (
          <V268PublicationCard key={pub.id} pub={pub} onOpen={setLightbox} />
        ))}
      </div>
      {lightbox && <V268Lightbox pub={lightbox} onClose={() => setLightbox(null)} />}
    </div>
  );
};

// V268b (F8) — « Mes publications » : liste des posts de l'utilisateur, avec
// edition (legende + nom affiche) et suppression. Rendu sous le formulaire de
// la modale. `subscriberCode` vide = coach (auth par en-tete/JWT via
// l'intercepteur) ; sinon abonne (code passe explicitement).
const V268MyPublications = ({ subscriberCode, refreshKey }) => {
  const [items, setItems] = useState(null); // null = chargement
  const [editing, setEditing] = useState(null); // id en cours d'edition
  const [editCaption, setEditCaption] = useState('');
  const [editName, setEditName] = useState('');
  const [confirmDel, setConfirmDel] = useState(null); // id a confirmer
  const [busy, setBusy] = useState(false);

  const load = () => {
    const url = subscriberCode
      ? `${API}/publications/mine?subscriber_code=${encodeURIComponent(subscriberCode)}`
      : `${API}/publications/mine`;
    axios.get(url)
      .then(res => setItems(Array.isArray(res.data) ? res.data : []))
      .catch(() => setItems([]));
  };
  // Recharge a l'ouverture ET apres chaque publication (refreshKey change).
  useEffect(load, [subscriberCode, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const startEdit = (p) => {
    setEditing(p.id);
    setEditCaption(p.caption || '');
    setEditName(p.display_name || p.subscriber_name || '');
    setConfirmDel(null);
  };

  const saveEdit = async (id) => {
    if (busy) return;
    setBusy(true);
    try {
      const body = { caption: editCaption.slice(0, 500), display_name: editName.slice(0, 60) };
      if (subscriberCode) body.subscriber_code = subscriberCode;
      await axios.put(`${API}/publications/${id}`, body);
      setEditing(null);
      load();
    } catch (e) { /* on laisse l'edition ouverte */ }
    setBusy(false);
  };

  const doDelete = async (id) => {
    if (busy) return;
    setBusy(true);
    try {
      const url = subscriberCode
        ? `${API}/publications/${id}?subscriber_code=${encodeURIComponent(subscriberCode)}`
        : `${API}/publications/${id}`;
      await axios.delete(url);
      setConfirmDel(null);
      setItems(list => (list || []).filter(p => p.id !== id)); // retrait immediat
    } catch (e) { /* garde l'element */ }
    setBusy(false);
  };

  if (items === null) return null;
  if (items.length === 0) return null;

  const inputStyle = { width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid #333', background: '#0a0a1a', color: '#fff', fontSize: '0.85rem', boxSizing: 'border-box' };

  return (
    <div style={{ marginTop: 20, borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 16 }}>
      <h4 style={{ color: '#fff', fontSize: '0.9rem', margin: '0 0 12px' }}>Mes publications</h4>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {items.map(p => (
          <div key={p.id} style={{ display: 'flex', gap: 10, background: '#0f0f1e', borderRadius: 10, padding: 8 }}>
            <div style={{ width: 54, height: 72, borderRadius: 6, overflow: 'hidden', background: '#000', flexShrink: 0 }}>
              {p.media_type === 'video' ? (
                <video src={p.media_url} poster={p.thumbnail_url || undefined} muted playsInline preload="metadata" style={{ display: 'block', width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : (
                <img src={p.media_url} alt="" style={{ display: 'block', width: '100%', height: '100%', objectFit: 'cover' }} />
              )}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              {editing === p.id ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <input value={editName} onChange={e => setEditName(e.target.value.slice(0, 60))} placeholder="Nom affiché" style={inputStyle} />
                  <textarea value={editCaption} onChange={e => setEditCaption(e.target.value.slice(0, 500))} placeholder="Légende" rows={2} style={{ ...inputStyle, resize: 'vertical' }} />
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button type="button" onClick={() => saveEdit(p.id)} disabled={busy}
                      style={{ flex: 1, padding: '7px', borderRadius: 8, border: 'none', background: 'var(--primary-color, #D91CD2)', color: '#fff', fontWeight: 700, fontSize: '0.8rem', cursor: 'pointer' }}>
                      Enregistrer
                    </button>
                    <button type="button" onClick={() => setEditing(null)}
                      style={{ padding: '7px 12px', borderRadius: 8, border: '1px solid #333', background: 'transparent', color: '#999', fontSize: '0.8rem', cursor: 'pointer' }}>
                      Annuler
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                    <p style={{ color: '#fff', fontSize: '0.8rem', fontWeight: 600, margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.display_name || p.subscriber_name}
                    </p>
                    <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                      <button type="button" onClick={() => startEdit(p)} title="Modifier" aria-label="Modifier"
                        style={{ background: 'none', border: 'none', padding: 4, cursor: 'pointer', color: 'var(--primary-color, #D91CD2)' }}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                        </svg>
                      </button>
                      <button type="button" onClick={() => { setConfirmDel(p.id); setEditing(null); }} title="Supprimer" aria-label="Supprimer"
                        style={{ background: 'none', border: 'none', padding: 4, cursor: 'pointer', color: '#f87171' }}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="3 6 5 6 21 6" />
                          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                        </svg>
                      </button>
                    </div>
                  </div>
                  {p.caption ? (
                    <p style={{ color: '#999', fontSize: '0.7rem', margin: '3px 0 0', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                      {p.caption}
                    </p>
                  ) : null}
                  <p style={{ margin: '4px 0 0' }}><V268Remaining remaining={p.remaining_hours} /></p>
                  {confirmDel === p.id && (
                    <div style={{ marginTop: 6, background: 'rgba(229,62,62,0.1)', borderRadius: 8, padding: 8 }}>
                      <p style={{ color: '#fca5a5', fontSize: '0.75rem', margin: '0 0 6px' }}>Supprimer cette publication ?</p>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button type="button" onClick={() => doDelete(p.id)} disabled={busy}
                          style={{ flex: 1, padding: '6px', borderRadius: 8, border: 'none', background: '#E53E3E', color: '#fff', fontWeight: 700, fontSize: '0.75rem', cursor: 'pointer' }}>
                          Supprimer
                        </button>
                        <button type="button" onClick={() => setConfirmDel(null)}
                          style={{ padding: '6px 12px', borderRadius: 8, border: '1px solid #333', background: 'transparent', color: '#999', fontSize: '0.75rem', cursor: 'pointer' }}>
                          Annuler
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}
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
  // V268 (F5): legende optionnelle, plafonnee a 500 (le serveur recoupe aussi).
  const [caption, setCaption] = useState('');
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
      //
      // V267 — LE BUG QUI CASSAIT TOUTE PUBLICATION. On utilisait `axios.post`,
      // or l'intercepteur global (App.js) ajoute `Authorization` et
      // `X-User-Email` a CHAQUE requete axios — y compris cet upload
      // cross-origin vers Cloudinary. Ces en-tetes personnalises font passer la
      // requete en preflight CORS, que l'endpoint d'upload Cloudinary refuse :
      // le navigateur la BLOQUE, axios n'a aucune reponse, et la modale affiche
      // le message de repli « La publication a échoué ». Cela cassait aussi bien
      // avec que sans JWT (l'en-tete X-User-Email est injecte dans les deux cas).
      // `fetch` n'est PAS soumis a l'intercepteur -> requete simple, pas de
      // preflight, pas d'en-tete parasite. C'est exactement ce que fait deja le
      // CloudinaryUploadButton qui fonctionne en production.
      const cloudResp = await fetch(endpoint, { method: 'POST', body: formData });
      const cloudData = await cloudResp.json().catch(function () { return {}; });
      if (!cloudResp.ok || !cloudData.secure_url) {
        throw new Error((cloudData.error && cloudData.error.message) || "L'envoi du média a échoué.");
      }
      // V261b: `cloudinary_public_id` n'est PLUS envoye — le serveur le derive
      // lui-meme de l'URL. Il finissait en argument de `destroy()` : un client
      // pouvait y designer le media d'un autre et le faire effacer.
      // V263: sans code abonne, on n'envoie RIEN qui designe l'auteur — le
      // serveur le deduit de la session (JWT ou en-tete). Envoyer un
      // `coach_email` ici rouvrirait la falsification corrigee en V262.
      // Le POST /publications, LUI, reste en axios : il est same-origin et a
      // BESOIN de X-User-Email (auth coach) — l'intercepteur global le pose.
      var payload = { media_url: cloudData.secure_url, media_type: mediaType };
      if (subscriberCode) payload.subscriber_code = subscriberCode;
      if (caption.trim()) payload.caption = caption.trim().slice(0, 500); // V268

      await axios.post(`${API}/publications`, payload);
      setUploading(false);
      if (onPublished) onPublished();
      onClose();
    } catch (err) {
      setUploading(false);
      setError(
        (err && err.response && err.response.data && err.response.data.detail)
        || (err && err.message)
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

        {/* V268 (F5): legende. Optionnelle, 500 max, compteur discret. */}
        <textarea
          value={caption}
          onChange={(e) => setCaption(e.target.value.slice(0, 500))}
          placeholder="Ajoutez une légende..."
          maxLength={500}
          rows={2}
          style={{
            width: '100%', marginTop: 12, padding: '10px 12px', borderRadius: 8,
            border: '1px solid #333', background: '#0a0a1a', color: '#fff',
            fontSize: '0.85rem', resize: 'vertical', boxSizing: 'border-box'
          }}
          data-testid="publish-caption"
        />
        <p style={{ color: '#555', fontSize: '0.62rem', textAlign: 'right', margin: '2px 2px 0' }}>
          {caption.length}/500
        </p>

        <p style={{ color: '#666', fontSize: '0.7rem', marginTop: 8, display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center' }}>
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

        {/* V268b (F8): mes publications, sous le formulaire — edition + suppression. */}
        <V268MyPublications subscriberCode={subscriberCode} refreshKey={0} />
      </div>
    </div>
  );
};

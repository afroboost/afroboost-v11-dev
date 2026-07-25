// V261 — Publications des abonnes (image / video 9:16, duree de vie 48 h)
//
// Module SEPARE, et non un ajout a App.js : `SubscriberSpace` a besoin de
// `PublishModal`, et App.js importe deja `SubscriberSpace`. Les loger dans
// App.js creerait une dependance circulaire — le genre de cycle qui rend un
// composant `undefined` a l'execution selon l'ordre d'evaluation des modules.

import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom'; // V268d
import axios from 'axios';
import Cropper from 'react-easy-crop'; // V268c (F1)

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const API = `${BACKEND_URL}/api`;

// V269 — upload vers Cloudinary en XMLHttpRequest, pour exposer la PROGRESSION
// (`fetch` ne remonte pas la progression d'upload). Ni axios ni fetch :
//   - axios porterait l'intercepteur global (Authorization / X-User-Email) ->
//     preflight CORS refuse par Cloudinary = le bug V267 ;
//   - XHR nu ne porte AUCUN de ces en-tetes -> requete simple, pas de preflight.
// `onProgress(percent)` est optionnel. Renvoie la reponse Cloudinary complete
// (on y lit secure_url ET duration pour la limite video).
function v269UploadToCloudinary(fileOrBlob, kind, onProgress) {
  return new Promise((resolve, reject) => {
    const fd = new FormData();
    fd.append('file', fileOrBlob);
    fd.append('upload_preset', 'afroboost');
    fd.append('folder', 'publications');
    const endpoint = kind === 'video'
      ? 'https://api.cloudinary.com/v1_1/dtm0r7hwq/video/upload'
      : 'https://api.cloudinary.com/v1_1/dtm0r7hwq/image/upload';
    const xhr = new XMLHttpRequest();
    xhr.open('POST', endpoint);
    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
      };
    }
    xhr.onload = () => {
      let data = {};
      try { data = JSON.parse(xhr.responseText); } catch (e) { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300 && data.secure_url) {
        resolve(data);
      } else {
        reject(new Error((data.error && data.error.message) || "L'envoi du média a échoué."));
      }
    };
    xhr.onerror = () => reject(new Error("L'envoi du média a échoué."));
    xhr.send(fd);
  });
}

// V268c (F1) — genere l'image recadree en blob JPEG depuis le crop en pixels.
function v268cGetCroppedImg(imageSrc, pixelCrop) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.crossOrigin = 'anonymous';
    image.onload = () => {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(pixelCrop.width));
        canvas.height = Math.max(1, Math.round(pixelCrop.height));
        const ctx = canvas.getContext('2d');
        ctx.drawImage(
          image,
          pixelCrop.x, pixelCrop.y, pixelCrop.width, pixelCrop.height,
          0, 0, pixelCrop.width, pixelCrop.height
        );
        canvas.toBlob(
          (blob) => (blob ? resolve(blob) : reject(new Error('canvas vide'))),
          'image/jpeg', 0.9
        );
      } catch (e) { reject(e); }
    };
    image.onerror = reject;
    image.src = imageSrc;
  });
}

// V268c (F1) — 4 captures d'une video, en best-effort. Certains codecs/
// navigateurs echouent au seek : on renvoie ce qu'on a pu extraire (peut etre
// vide) sans jamais bloquer la publication.
async function v268cGenerateThumbnails(videoFile, count = 4) {
  const video = document.createElement('video');
  video.muted = true;
  video.playsInline = true;
  video.src = URL.createObjectURL(videoFile);
  const out = [];
  try {
    await new Promise((res, rej) => {
      video.onloadedmetadata = res;
      video.onerror = rej;
    });
    const duration = isFinite(video.duration) && video.duration > 0 ? video.duration : 0;
    for (let i = 0; i < count; i++) {
      const time = duration ? Math.min(duration - 0.05, (duration / count) * i + 0.5) : 0;
      try {
        await new Promise((res, rej) => {
          video.onseeked = res;
          video.onerror = rej;
          video.currentTime = time;
        });
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth || 320;
        canvas.height = video.videoHeight || 320;
        canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
        const blob = await new Promise((r) => canvas.toBlob(r, 'image/jpeg', 0.8));
        if (blob) out.push({ time, blob, url: URL.createObjectURL(blob) });
      } catch (e) { /* on saute cette capture */ }
    }
  } catch (e) { /* metadata illisible : aucune miniature */ }
  finally { URL.revokeObjectURL(video.src); }
  return out;
}

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
  // V268b Fix B3 : en plein ecran, la video demarre AVEC le son. La lightbox
  // s'ouvre sur un clic (geste utilisateur), ce qui autorise la lecture non
  // muette. Le bouton reste dispo pour couper. La carte, elle, garde son propre
  // etat muet (element video distinct) — rien a restaurer a la fermeture.
  const [muted, setMuted] = useState(pub.media_type !== 'video' ? true : false);
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  useEffect(() => {
    if (pub.media_type !== 'video') return;
    const v = videoRef.current;
    if (!v) return;
    v.muted = false;
    v.volume = 1.0;
    const p = v.play();
    if (p && p.catch) {
      // Certains navigateurs refusent l'autoplay non muet malgre le geste :
      // on retombe alors sur une lecture muette plutot qu'une video figee.
      p.catch(() => {
        v.muted = true;
        setMuted(true);
        try { v.play(); } catch (e) { /* ignore */ }
      });
    }
  }, [pub]);
  const toggleMute = v268ToggleSound(videoRef, setMuted); // V268b Fix B2
  return (
    // V268d : z-index tres eleve pour passer AU-DESSUS de tout (menu inclus).
    // Combine au portal vers document.body (voir le rendu du carrousel), la
    // lightbox couvre desormais reellement tout l'ecran.
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 2147483000, background: 'rgba(0,0,0,0.92)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16
      }}
      data-testid="publication-lightbox"
    >
      {/* V268d : X SANS rond, plus haut (top/right 10), juste l'icone blanche
          avec un drop-shadow pour la lisibilite. */}
      <button
        onClick={onClose}
        aria-label="Fermer"
        style={{
          position: 'absolute', top: 10, right: 10, zIndex: 2,
          background: 'transparent', border: 'none', padding: 4, cursor: 'pointer',
          color: '#fff', filter: 'drop-shadow(0 0 3px rgba(0,0,0,0.9))'
        }}
      >
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
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
  // V268c Fix 2 : plus de bouton son sur la carte — la video du carrousel est
  // TOUJOURS muette (autoplay silencieux). Le son n'existe qu'en lightbox.
  // Plus besoin de ref ni d'etat muet ici.
  return (
    // V268b Fix A (revu) : le texte (nom, heures, legende) sort du media et
    // passe DESSOUS, dans un bloc separe. L'ancien texte etait pose EN
    // SUPERPOSITION sur le media via un degrade ; combine a un media mal
    // contenu, il debordait sur la section « Choisissez votre offre » juste
    // apres le carrousel. Media a hauteur FIXE + overflow hidden = plus rien
    // ne depasse.
    // V268d : largeur VERROUILLEE (min = max = width) pour qu'aucun parent flex
    // ne l'etire ni ne l'ecrase, et hauteur du media FIXE.
    <div style={{ flexShrink: 0, width: 240, minWidth: 240, maxWidth: 240, scrollSnapAlign: 'start' }}>
      {/* Conteneur media a HAUTEUR FIXE + overflow hidden ; le media porte
          height:250px EXPLICITE. `display:block` supprime l'espace fantome d'un
          media `inline`. Rien ne peut deborder. */}
      <div
        onClick={() => onOpen(pub)}
        style={{
          position: 'relative', width: '100%', height: 250, maxHeight: 250, overflow: 'hidden',
          borderRadius: 12, flexShrink: 0, background: '#000', cursor: 'pointer'
        }}
        data-testid="publication-card"
      >
        {pub.media_type === 'video' ? (
          <video
            src={pub.media_url}
            poster={pub.thumbnail_url || undefined}
            muted autoPlay loop playsInline
            style={{ display: 'block', width: '100%', height: '250px', objectFit: 'cover', borderRadius: 12 }}
          />
        ) : (
          <img
            src={pub.media_url}
            alt={`Publication de ${pub.display_name || pub.subscriber_name || 'un abonné'}`}
            loading="lazy"
            style={{ display: 'block', width: '100%', height: '250px', objectFit: 'cover', borderRadius: 12 }}
          />
        )}
      </div>
      {/* Bloc d'infos SOUS le media, jamais en superposition. */}
      <div style={{ padding: '6px 2px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
          <p style={{ color: '#fff', fontSize: '0.7rem', fontWeight: 600, margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {pub.display_name || pub.subscriber_name}
          </p>
          {/* V268b Fix C : « 47h » seul, couleur dynamique du coach. */}
          <V268Remaining remaining={pub.remaining_hours} />
        </div>
        {pub.caption ? (
          <p
            onClick={() => onOpen(pub)}
            style={{ color: '#bbb', fontSize: '0.62rem', margin: '4px 0 0', lineHeight: 1.3, cursor: 'pointer', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}
          >
            {pub.caption}
          </p>
        ) : null}
      </div>
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
      {/* V268d — LE FIX. La lightbox etait rendue ICI, a l'interieur de
          `.fade-in-section` dont l'animation fadeInUp laisse un `transform:
          translateY(0)` PERMANENT (fill-mode forwards). Un `transform` non-none
          fait de cet element le bloc conteneur des descendants `position:
          fixed` : la lightbox etait donc piegee dans la boite du carrousel au
          lieu de couvrir l'ecran — d'ou la video geante derriere le menu.
          Le PORTAL vers document.body la sort de ce contexte d'empilement : son
          `position: fixed` se cale enfin sur le viewport. */}
      {lightbox && createPortal(
        <V268Lightbox pub={lightbox} onClose={() => setLightbox(null)} />,
        document.body
      )}
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
  // V269 Fix 1 : recharge aussi quand une publication est creee ailleurs (le
  // formulaire au-dessus dispatche l'evenement a la reussite).
  useEffect(() => {
    window.addEventListener('afroboost:publications-changed', load);
    return () => window.removeEventListener('afroboost:publications-changed', load);
  }, [subscriberCode]); // eslint-disable-line react-hooks/exhaustive-deps

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
      // V269 Fix 1 : la vitrine reflete l'edition sans rechargement.
      try { window.dispatchEvent(new CustomEvent('afroboost:publications-changed')); } catch (e) { /* ignore */ }
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
      // V269 Fix 1 : la vitrine retire aussi la publication sans rechargement.
      try { window.dispatchEvent(new CustomEvent('afroboost:publications-changed')); } catch (e) { /* ignore */ }
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
  const [file, setFile] = useState(null);           // fichier brut selectionne
  const [preview, setPreview] = useState(null);      // apercu affiche
  const [mediaType, setMediaType] = useState('image');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [caption, setCaption] = useState('');
  const fileInputRef = useRef(null);

  // V268c (F1) — recadrage image
  const [rawImageSrc, setRawImageSrc] = useState(null); // URL objet de l'original
  const [showCrop, setShowCrop] = useState(false);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [aspect, setAspect] = useState(1);              // 1 / (4/5) / (16/9)
  const [croppedAreaPixels, setCroppedAreaPixels] = useState(null);
  const [croppedBlob, setCroppedBlob] = useState(null); // image finale a uploader

  // V268c (F1) — miniatures video
  const [thumbs, setThumbs] = useState([]);
  const [thumbIdx, setThumbIdx] = useState(0);
  const [thumbLoading, setThumbLoading] = useState(false);

  // V269 — progression d'upload + succes
  const [uploadPct, setUploadPct] = useState(0);
  const [uploadName, setUploadName] = useState('');
  const [success, setSuccess] = useState(false);

  const revokeAll = () => {
    if (preview) URL.revokeObjectURL(preview);
    if (rawImageSrc) URL.revokeObjectURL(rawImageSrc);
    thumbs.forEach(t => t.url && URL.revokeObjectURL(t.url));
  };
  // Nettoyage memoire au demontage.
  useEffect(() => () => revokeAll(), []); // eslint-disable-line react-hooks/exhaustive-deps

  const clearFile = () => {
    revokeAll();
    setFile(null); setPreview(null);
    setRawImageSrc(null); setShowCrop(false); setCroppedBlob(null);
    setThumbs([]); setThumbIdx(0); setThumbLoading(false);
  };

  const handleFileSelect = (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    setError('');
    revokeAll();
    setCroppedBlob(null); setThumbs([]); setThumbIdx(0);

    if (f.type.startsWith('video/')) {
      // V269 Fix 3 — limite 1 min. On lit d'abord la duree via un element video
      // « metadata only » ; on ne procede QUE si <= 60 s.
      const probe = document.createElement('video');
      probe.preload = 'metadata';
      const probeUrl = URL.createObjectURL(f);
      probe.src = probeUrl;
      probe.onloadedmetadata = () => {
        const dur = probe.duration;
        URL.revokeObjectURL(probeUrl);
        if (isFinite(dur) && dur > 60) {
          setError('La vidéo ne doit pas dépasser 1 minute (60 s). La vôtre fait ' + Math.round(dur) + ' s.');
          if (fileInputRef.current) fileInputRef.current.value = '';
          return;
        }
        proceedWithVideo(f);
      };
      probe.onerror = () => { URL.revokeObjectURL(probeUrl); proceedWithVideo(f); }; // duree illisible : on laisse passer
      return;
    }
    // IMAGE : recadrage d'abord.
    setMediaType('image');
    setFile(f);
    const src = URL.createObjectURL(f);
    setRawImageSrc(src);
    setPreview(null);
    setCrop({ x: 0, y: 0 }); setZoom(1); setAspect(1);
    setShowCrop(true);
  };

  const proceedWithVideo = (f) => {
    // VIDEO validee : apercu + generation des miniatures, puis choix.
    setMediaType('video');
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setShowCrop(false);
    setThumbLoading(true);
    v268cGenerateThumbnails(f).then(list => {
      setThumbs(list);
      // Defaut : la capture la plus proche d'1 s.
      let idx = 0, best = Infinity;
      list.forEach((t, i) => { const d = Math.abs((t.time || 0) - 1); if (d < best) { best = d; idx = i; } });
      setThumbIdx(idx);
      setThumbLoading(false);
    }).catch(() => { setThumbs([]); setThumbLoading(false); });
  };

  // V268c (F1) — valide le recadrage : genere le blob et l'utilise comme apercu.
  const applyCrop = async () => {
    try {
      const blob = await v268cGetCroppedImg(rawImageSrc, croppedAreaPixels);
      setCroppedBlob(blob);
      if (preview) URL.revokeObjectURL(preview);
      setPreview(URL.createObjectURL(blob));
      setShowCrop(false);
    } catch (e) {
      // Repli : on garde l'original (file) et on affiche son apercu.
      setCroppedBlob(null);
      setPreview(rawImageSrc);
      setShowCrop(false);
    }
  };

  const handleUploadAndPublish = async () => {
    // Image -> blob recadre si dispo, sinon original. Video -> le fichier.
    const media = mediaType === 'image' ? (croppedBlob || file) : file;
    if (!media || uploading) return;
    setUploading(true);
    setError('');
    setUploadPct(0);
    setUploadName(file && file.name ? file.name : (mediaType === 'video' ? 'vidéo' : 'image'));
    try {
      // V269 Fix 2 : progression du media principal (0->100 %).
      const mediaData = await v269UploadToCloudinary(media, mediaType, setUploadPct);
      const mediaUrl = mediaData.secure_url;

      // V269 Fix 3 (double garde serveur cote client) : Cloudinary renvoie la
      // duree ; si > 60 s, on refuse plutot que de publier une video trop
      // longue passee entre les mailles de la sonde locale.
      if (mediaType === 'video' && isFinite(mediaData.duration) && mediaData.duration > 60) {
        throw new Error('La vidéo dépasse 1 minute (60 s).');
      }

      // Miniature video choisie, uploadee a part. Best-effort.
      let thumbnailUrl = '';
      if (mediaType === 'video' && thumbs[thumbIdx] && thumbs[thumbIdx].blob) {
        try { const td = await v269UploadToCloudinary(thumbs[thumbIdx].blob, 'image'); thumbnailUrl = td.secure_url; }
        catch (e) { /* ignore */ }
      }

      // Le POST /publications reste en axios : same-origin, il a besoin de
      // X-User-Email (auth), pose par l'intercepteur global.
      var payload = { media_url: mediaUrl, media_type: mediaType };
      if (subscriberCode) payload.subscriber_code = subscriberCode;
      if (caption.trim()) payload.caption = caption.trim().slice(0, 500);
      if (thumbnailUrl) payload.thumbnail_url = thumbnailUrl;

      await axios.post(`${API}/publications`, payload);

      // V269 Fix 1 : signale a la vitrine ET a « Mes publications » de se
      // rafraichir, sans rechargement de page (voir l'ecouteur dans App.js et
      // V268MyPublications).
      try { window.dispatchEvent(new CustomEvent('afroboost:publications-changed')); } catch (e) { /* ignore */ }

      setUploading(false);
      setSuccess(true); // « Publication réussie ! » un court instant
      if (onPublished) onPublished();
      setTimeout(() => { onClose(); }, 900);
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

        {/* V268c (F1A) — ecran de recadrage image, en overlay plein ecran.
            react-easy-crop exige un conteneur POSITIONNE et dimensionne. */}
        {showCrop && rawImageSrc && (
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              position: 'fixed', inset: 0, zIndex: 10000, background: '#000',
              display: 'flex', flexDirection: 'column'
            }}
            data-testid="publish-cropper"
          >
            <div style={{ position: 'relative', flex: 1 }}>
              <Cropper
                image={rawImageSrc}
                crop={crop}
                zoom={zoom}
                aspect={aspect}
                onCropChange={setCrop}
                onZoomChange={setZoom}
                onCropComplete={(_, px) => setCroppedAreaPixels(px)}
              />
            </div>
            <div style={{ padding: 14, background: '#0a0a1a' }}>
              {/* Formats */}
              <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginBottom: 12 }}>
                {[{ a: 1, l: 'Carré' }, { a: 4 / 5, l: 'Portrait' }, { a: 16 / 9, l: 'Paysage' }].map(o => (
                  <button
                    key={o.l}
                    type="button"
                    onClick={() => setAspect(o.a)}
                    style={{
                      padding: '7px 14px', borderRadius: 20, cursor: 'pointer', fontSize: '0.8rem',
                      border: '1px solid ' + (Math.abs(aspect - o.a) < 0.01 ? 'var(--primary-color, #D91CD2)' : '#333'),
                      background: Math.abs(aspect - o.a) < 0.01 ? 'var(--primary-color, #D91CD2)' : 'transparent',
                      color: '#fff', fontWeight: 600
                    }}
                  >
                    {o.l}
                  </button>
                ))}
              </div>
              {/* Zoom */}
              <input
                type="range" min={1} max={3} step={0.01} value={zoom}
                onChange={(e) => setZoom(Number(e.target.value))}
                style={{ width: '100%', accentColor: 'var(--primary-color, #D91CD2)' }}
                aria-label="Zoom"
              />
              <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
                <button type="button" onClick={clearFile}
                  style={{ flex: 1, padding: '11px', borderRadius: 12, border: '1px solid #333', background: 'transparent', color: '#999', cursor: 'pointer', fontWeight: 600 }}>
                  Annuler
                </button>
                <button type="button" onClick={applyCrop}
                  style={{ flex: 1, padding: '11px', borderRadius: 12, border: 'none', background: 'var(--primary-color, #D91CD2)', color: '#fff', cursor: 'pointer', fontWeight: 700 }}>
                  Valider
                </button>
              </div>
            </div>
          </div>
        )}

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

        {/* V268c (F1B) — choix de la miniature video. Best-effort : si la
            generation n'a rien donne (codec, navigateur), on n'affiche rien et
            la video part sans poster dedie. */}
        {mediaType === 'video' && preview && (thumbLoading || thumbs.length > 0) && (
          <div style={{ marginTop: 12 }}>
            <p style={{ color: '#999', fontSize: '0.75rem', margin: '0 0 6px' }}>
              {thumbLoading ? 'Génération des miniatures…' : 'Choisir la miniature'}
            </p>
            {!thumbLoading && (
              <div style={{ display: 'flex', gap: 6 }}>
                {thumbs.map((t, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setThumbIdx(i)}
                    style={{
                      flex: 1, padding: 0, borderRadius: 8, overflow: 'hidden', cursor: 'pointer',
                      border: '2px solid ' + (thumbIdx === i ? 'var(--primary-color, #D91CD2)' : 'transparent'),
                      background: '#000', lineHeight: 0
                    }}
                    aria-label={`Miniature ${i + 1}`}
                  >
                    <img src={t.url} alt="" style={{ display: 'block', width: '100%', height: 64, objectFit: 'cover' }} />
                  </button>
                ))}
              </div>
            )}
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
          <p style={{ color: '#E53E3E', fontSize: '0.8rem', textAlign: 'center', marginTop: 8 }}>{error}</p>
        )}

        {/* V269 Fix 2 : barre de progression pendant l'upload. */}
        {uploading && (
          <div style={{ marginTop: 12 }} data-testid="publish-progress">
            <div style={{ fontSize: '0.78rem', color: '#ccc', marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {uploadName}
            </div>
            <div style={{ width: '100%', height: 6, background: '#333', borderRadius: 3, overflow: 'hidden' }}>
              <div style={{ width: uploadPct + '%', height: '100%', background: 'var(--primary-color, #D91CD2)', borderRadius: 3, transition: 'width 0.3s ease' }} />
            </div>
            <div style={{ fontSize: '0.7rem', color: '#999', marginTop: 4, textAlign: 'right' }}>{uploadPct}%</div>
          </div>
        )}

        {/* V269 : confirmation breve avant fermeture. */}
        {success && (
          <p style={{ color: '#4ade80', fontSize: '0.85rem', textAlign: 'center', marginTop: 10, fontWeight: 600 }}>
            Publication réussie !
          </p>
        )}

        {preview && !success && (
          <button
            onClick={handleUploadAndPublish}
            disabled={uploading}
            style={{
              width: '100%', padding: '12px', borderRadius: 25,
              background: uploading ? '#666' : 'var(--primary-color, #D91CD2)',
              color: '#fff', border: 'none', cursor: uploading ? 'not-allowed' : 'pointer',
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

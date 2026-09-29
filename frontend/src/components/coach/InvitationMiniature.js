/**
 * INV-3 — Miniature d'une INVITATION (carte d'aperçu WhatsApp / Open Graph 1200×630).
 *
 * Ce qui est RÉUTILISÉ, rien de reconstruit :
 *  - `uploadToCloudinary` (CloudinaryUploadButton.js) : même envoi que les
 *    campagnes, progression réelle `onProgress` + annulation `signal` ;
 *  - `react-easy-crop` : recadrage déplacer + zoomer ;
 *  - le style d'états de CampaignMediaUploader (V533) : idle → envoi N % →
 *    terminé | erreur (Réessayer) | annulé. Jamais un spinner muet.
 *
 * `recadrerImage` (utils/miniatureReel.js) rend un Blob de la TAILLE du cadre
 * choisi, pas une taille imposée : la carte doit faire EXACTEMENT 1200×630,
 * donc INV-3 dessine le recadrage sur un canvas 1200×630 (`recadrer1200x630`).
 *
 * API : onChange({ image_url, image_source }) — 'upload' (URL renvoyée par
 * l'envoi, du recadrage 1200×630 réellement envoyé) ou 'default' (image_url null).
 * onBusyChange(bool) : envoi en cours → le parent bloque « Enregistrer ».
 */
import React, { useEffect, useRef, useState } from 'react';
import Cropper from 'react-easy-crop';
import SvgIcon from '../SvgIcon';
import { uploadToCloudinary } from '../CloudinaryUploadButton';

// INV-3 : couleurs UNIQUEMENT via les variables du coach (le hex n'est qu'un secours).
const COULEUR = 'var(--primary-color, #D91CD2)';
const RGB = 'var(--primary-rgb, 217, 28, 210)';
const TYPES_IMAGE = 'image/jpeg,image/jpg,image/png,image/webp';
const MAX_MO = 25;
export const LARGEUR_CARTE = 1200;
export const HAUTEUR_CARTE = 630;
export const RATIO_CARTE = LARGEUR_CARTE / HAUTEUR_CARTE;

/** INV-3 : recadre `imageSrc` sur `pixelCrop` et le dessine en 1200×630 → Blob JPEG. */
export function recadrer1200x630(imageSrc, pixelCrop, qualite = 0.9) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.crossOrigin = 'anonymous';
    image.onload = () => {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = LARGEUR_CARTE;
        canvas.height = HAUTEUR_CARTE;
        const ctx = canvas.getContext('2d');
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(image, pixelCrop.x, pixelCrop.y, pixelCrop.width, pixelCrop.height,
          0, 0, LARGEUR_CARTE, HAUTEUR_CARTE);
        canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('canvas vide'))), 'image/jpeg', qualite);
      } catch (e) { reject(e); }
    };
    image.onerror = () => reject(new Error('Image illisible.'));
    image.src = imageSrc;
  });
}

function libelle(etat, pct) {
  switch (etat) {
    case 'uploading': return 'Envoi de la miniature… ' + Math.max(0, Math.min(100, Math.round(pct || 0))) + ' %';
    case 'done': return 'Miniature enregistrée';
    case 'error': return "L'envoi a échoué";
    case 'cancelled': return 'Envoi annulé';
    default: return '';
  }
}

function Barre({ pct }) {
  const p = Math.max(0, Math.min(100, Math.round(pct || 0)));
  return (
    <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={p}
      style={{ height: 8, borderRadius: 999, background: 'rgba(255,255,255,0.1)', overflow: 'hidden' }}>
      <div style={{ width: p + '%', height: '100%', background: COULEUR, transition: 'width 0.15s linear' }} />
    </div>
  );
}

export default function InvitationMiniature({ value, source, defaultUrl, onChange, onBusyChange }) {
  const inputRef = useRef(null);
  const abortRef = useRef(null);
  const dernierBlobRef = useRef(null);
  const cropUrlRef = useRef('');   // INV-3 (audit P2) : URL temporaire en cours, à révoquer
  const [etat, setEtat] = useState('idle'); // idle | uploading | done | error | cancelled
  const [pct, setPct] = useState(0);
  const [erreur, setErreur] = useState('');
  const [cropSrc, setCropSrc] = useState('');
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [cropPixels, setCropPixels] = useState(null);

  const enEnvoi = etat === 'uploading';
  // INV-3 : dépend d'un BOOLÉEN (jamais d'un objet) — aucune boucle d'effets.
  useEffect(() => { if (onBusyChange) onBusyChange(enEnvoi); }, [enEnvoi, onBusyChange]);
  // INV-3 (audit P2) : libère l'URL temporaire (blob:) du recadrage — fermeture,
  // validation, remplacement par un autre fichier et démontage.
  const libererCropUrl = () => {
    const u = cropUrlRef.current;
    cropUrlRef.current = '';
    if (u && typeof URL !== 'undefined' && typeof URL.revokeObjectURL === 'function') {
      try { URL.revokeObjectURL(u); } catch (e) { /* ignore */ }
    }
  };
  const fermerCrop = () => { libererCropUrl(); setCropSrc(''); };
  useEffect(() => () => {
    if (abortRef.current) abortRef.current.abort();
    libererCropUrl();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const perso = source === 'upload' && !!value;
  const affichee = perso ? value : (defaultUrl || '');

  const choisir = () => { setErreur(''); if (inputRef.current) inputRef.current.click(); };

  const surFichier = (e) => {
    const f = e.target.files && e.target.files[0];
    if (inputRef.current) inputRef.current.value = '';
    if (!f) return;
    if (!/^image\/(jpe?g|png|webp)$/i.test(f.type || '')) { setErreur('Format accepté : JPG, PNG ou WEBP.'); return; }
    if (f.size > MAX_MO * 1024 * 1024) {
      setErreur('Image trop lourde (' + (f.size / 1024 / 1024).toFixed(1) + ' Mo, maximum ' + MAX_MO + ' Mo).');
      return;
    }
    setErreur(''); setCrop({ x: 0, y: 0 }); setZoom(1); setCropPixels(null);
    libererCropUrl();                       // un recadrage précédent laissé ouvert
    const u = URL.createObjectURL(f);
    cropUrlRef.current = u;
    setCropSrc(u);
  };

  const envoyer = async (blob) => {
    dernierBlobRef.current = blob;
    setErreur(''); setPct(0); setEtat('uploading');
    const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    abortRef.current = ctrl;
    try {
      const file = new File([blob], 'invitation-1200x630.jpg', { type: 'image/jpeg' });
      const { url } = await uploadToCloudinary(file, {
        folder: 'campaigns', maxSizeMB: MAX_MO,
        onProgress: (p) => setPct(p),
        signal: ctrl ? ctrl.signal : undefined,
      });
      setPct(100); setEtat('done');
      if (onChange) onChange({ image_url: url, image_source: 'upload' });
    } catch (e) {
      if (/annul|abort/i.test((e && e.message) || '')) { setEtat('cancelled'); setErreur(''); }
      else { setEtat('error'); setErreur((e && e.message) || "L'envoi a échoué."); }
    } finally {
      abortRef.current = null;
    }
  };

  const validerCrop = async () => {
    if (!cropSrc || !cropPixels) return;
    try {
      const blob = await recadrer1200x630(cropSrc, cropPixels);
      fermerCrop();
      await envoyer(blob);
    } catch (e) {
      fermerCrop();
      setEtat('error'); setErreur('Recadrage impossible : ' + ((e && e.message) || 'erreur'));
    }
  };
  const annuler = () => { if (abortRef.current) abortRef.current.abort(); };
  const reessayer = () => { if (dernierBlobRef.current) envoyer(dernierBlobRef.current); else choisir(); };
  const revenirDefaut = () => {
    setEtat('idle'); setErreur(''); setPct(0);
    if (onChange) onChange({ image_url: null, image_source: 'default' });
  };

  const bouton = {
    minHeight: 44, background: 'transparent', border: `1px solid rgba(${RGB}, 0.5)`, color: '#fff',
    borderRadius: 10, padding: '10px 14px', fontSize: 13, cursor: 'pointer',
    display: 'inline-flex', alignItems: 'center', gap: 6,
  };
  const boutonPrimaire = { ...bouton, background: COULEUR, border: 'none', fontWeight: 600 };

  return (
    <div data-testid="inv-mini" data-etat={etat} data-source={perso ? 'upload' : 'default'} style={{ display: 'grid', gap: 10 }}>
      <input ref={inputRef} type="file" accept={TYPES_IMAGE} style={{ display: 'none' }} tabIndex={-1} aria-hidden="true"
        data-testid="inv-mini-input" onChange={surFichier} />

      <div style={{ position: 'relative', width: '100%', maxWidth: 480, aspectRatio: '1200 / 630', borderRadius: 12,
        overflow: 'hidden', background: `rgba(${RGB}, 0.12)`, border: `1px solid rgba(${RGB}, 0.3)` }}>
        {affichee ? (
          <img src={affichee} alt={perso ? 'Miniature personnalisée' : 'Miniature par défaut'} data-testid="inv-mini-image"
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
        ) : (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'rgba(255,255,255,0.6)' }}>
            <SvgIcon name="image" size={28} />
          </div>
        )}
        <span style={{ position: 'absolute', left: 8, top: 8, fontSize: 11, fontWeight: 600, color: '#fff',
          background: 'rgba(0,0,0,0.55)', borderRadius: 999, padding: '3px 9px' }}>
          {perso ? 'Image personnalisée' : 'Image par défaut'}
        </span>
      </div>
      <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11 }}>Format de l'aperçu : 1200 × 630 (WhatsApp, réseaux sociaux).</div>

      {(enEnvoi || etat === 'done' || etat === 'cancelled') && (
        <div data-testid="inv-mini-progression" style={{ display: 'grid', gap: 6 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#fff', fontSize: 12, fontWeight: 600 }}>
            {enEnvoi && <SvgIcon name="loader" size={14} className="animate-spin" />}
            {etat === 'done' && <SvgIcon name="check" size={14} color={COULEUR} />}
            <span>{libelle(etat, pct)}</span>
          </div>
          {enEnvoi && <Barre pct={pct} />}
        </div>
      )}

      {erreur && (
        <div role="alert" data-testid="inv-mini-erreur" style={{ color: '#fca5a5', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
          <SvgIcon name="warning" size={14} />{etat === 'error' ? libelle('error') + ' — ' : ''}{erreur}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {enEnvoi ? (
          <button type="button" onClick={annuler} style={bouton} data-testid="inv-mini-annuler">
            <SvgIcon name="x" size={14} />Annuler
          </button>
        ) : (
          <>
            {etat === 'error' && (
              <button type="button" onClick={reessayer} style={boutonPrimaire} data-testid="inv-mini-reessayer">
                <SvgIcon name="refresh" size={14} />Réessayer
              </button>
            )}
            <button type="button" onClick={choisir} style={etat === 'error' ? bouton : boutonPrimaire} data-testid="inv-mini-choisir">
              <SvgIcon name={perso ? 'refresh' : 'upload'} size={14} />{perso ? "Remplacer l'image" : 'Choisir une image'}
            </button>
            {perso && (
              <button type="button" onClick={revenirDefaut} style={bouton} data-testid="inv-mini-defaut">
                <SvgIcon name="undo" size={14} />Revenir à l'image par défaut
              </button>
            )}
          </>
        )}
      </div>

      {cropSrc && (
        <div data-testid="inv-mini-cropper" role="dialog" aria-label="Recadrer la miniature" onClick={(e) => e.stopPropagation()}
          style={{ position: 'fixed', inset: 0, zIndex: 10001, background: '#000', display: 'flex', flexDirection: 'column' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <Cropper image={cropSrc} crop={crop} zoom={zoom} aspect={RATIO_CARTE} minZoom={1} maxZoom={3}
              onCropChange={setCrop} onZoomChange={setZoom} onCropComplete={(_, px) => setCropPixels(px)} />
          </div>
          <div style={{ padding: 14, background: 'rgba(0,0,0,0.85)', display: 'grid', gap: 10 }}>
            <div style={{ color: '#fff', fontSize: 12, textAlign: 'center' }}>
              Cadre 1200 × 630 — déplacez l'image et zoomez ; ce que vous voyez dans le cadre sera l'aperçu partagé.
            </div>
            <input type="range" min={1} max={3} step={0.01} value={zoom} onChange={(e) => setZoom(Number(e.target.value))}
              aria-label="Zoom" data-testid="inv-mini-zoom" style={{ width: '100%', accentColor: COULEUR, minHeight: 44 }} />
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
              <button type="button" onClick={fermerCrop} style={bouton} data-testid="inv-mini-recadrer-annuler">
                <SvgIcon name="x" size={14} />Annuler
              </button>
              <button type="button" onClick={validerCrop} disabled={!cropPixels} style={boutonPrimaire} data-testid="inv-mini-recadrer-valider">
                <SvgIcon name="check" size={14} />Utiliser ce cadrage
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

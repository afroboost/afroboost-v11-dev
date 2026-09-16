/**
 * V533 — Zone « Média » de la campagne : envoi avec PROGRESSION RÉELLE + miniature du Reel.
 *
 * Ce que ça corrige (dashboard → Campagnes → Modifier → Médias & Objectif) :
 *  1. une grosse vidéo partait sans aucune progression visible (un « Upload… » muet) ;
 *  2. impossible de savoir si l'envoi tournait, bloquait, ou avait échoué ;
 *  3. impossible de choisir la miniature/couverture du Reel.
 *
 * Ce qui est RÉUTILISÉ, rien de reconstruit :
 *  - `uploadToCloudinary` (CloudinaryUploadButton.js, V414/V420) : même endpoint
 *    `/api/coach/upload-asset` (+ morceaux de 4 Mo au-delà de 8 Mo), progression
 *    XHR `upload.onprogress` déjà calculée sur l'ENSEMBLE du fichier ; V533 y ajoute
 *    seulement l'annulation (`signal`) ;
 *  - `capturerFrame` / `attendreFrame` (VideoTrimEditor.js, V419) : la frame
 *    réellement décodée d'un <video>, en JPEG ;
 *  - `react-easy-crop` (déjà utilisé par Publications V268c et ChatWidget V279)
 *    pour le recadrage 9:16 déplacer + zoomer.
 *
 * États : idle → uploading (N %) → done → succès (aperçu) | error (Réessayer) | cancelled.
 * Jamais un spinner sans explication ; « Suivant » reste bloqué tant que l'envoi
 * n'est pas terminé (le parent lit `onBusyChange`).
 *
 * Données : `mediaUrl` (inchangé), `thumbnail_url`, `thumbnail_source`
 * (video_frame | upload), `thumbnail_time` (s) — persistées sur la campagne.
 */
import React, { useEffect, useRef, useState } from 'react';
import Cropper from 'react-easy-crop';
import SvgIcon from '../SvgIcon';
import { uploadToCloudinary } from '../CloudinaryUploadButton';
import { capturerFrame, attendreFrame } from '../VideoTrimEditor';
import {
  estPortrait, dejaNeufSeize, tailleLisible, dureeLisible, libelleEtat,
  recadrerImage, COUVERTURE_CONNECTEUR, RATIO_REEL,
} from '../../utils/miniatureReel';

const COULEUR = 'var(--primary-color, #D91CD2)';
const RGB = 'var(--primary-rgb, 217, 28, 210)';
const TYPES_IMAGE = 'image/jpeg,image/jpg,image/png,image/webp';

const estVideoUrl = (u) => /\.(mp4|webm|mov|m4v|ogv)(\?|$)/i.test(u || '') || /\/video\/upload\//i.test(u || '');

/** Barre de progression (réelle : la valeur vient de `upload.onprogress`). */
function Barre({ pct }) {
  const p = Math.max(0, Math.min(100, Math.round(pct || 0)));
  return (
    <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={p} data-testid="v533-barre"
      style={{ height: 8, borderRadius: 999, background: 'rgba(255,255,255,0.1)', overflow: 'hidden' }}>
      <div data-testid="v533-barre-remplie" style={{ width: p + '%', height: '100%', background: COULEUR, transition: 'width 0.15s linear' }} />
    </div>
  );
}

/** Aperçu couverture : Reel 9:16 plein écran + grille profil (recadrage centré). Aperçus visuels, pas pixel-perfect. */
function ApercuCouverture({ src, zonesSures, onToggleZones }) {
  if (!src) return null;
  const cadre = { position: 'relative', overflow: 'hidden', borderRadius: 10, background: '#000', border: '1px solid rgba(255,255,255,0.12)' };
  return (
    <div data-testid="v533-apercu-couverture" style={{ marginTop: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ color: 'rgba(255,255,255,0.75)', fontSize: 12, fontWeight: 600 }}>Aperçu couverture</span>
        <button type="button" onClick={onToggleZones} data-testid="v533-zones-sures"
          style={{ background: 'transparent', border: `1px solid rgba(${RGB}, 0.5)`, color: '#fff', borderRadius: 8, padding: '4px 10px', fontSize: 11, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
          <SvgIcon name={zonesSures ? 'eyeOff' : 'eye'} size={12} />{zonesSures ? 'Masquer les zones sûres' : 'Afficher les zones sûres'}
        </button>
      </div>
      <div style={{ display: 'flex', gap: 14, marginTop: 8, flexWrap: 'wrap' }}>
        <div>
          <div style={{ ...cadre, width: 135, height: 240 }} data-testid="v533-apercu-reel">
            <img src={src} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
            {zonesSures && (
              <div data-testid="v533-overlay-zones" aria-hidden="true" style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
                <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: '22%', background: `rgba(${RGB}, 0.35)`, borderTop: `1px dashed rgba(${RGB}, 0.9)` }} />
                <div style={{ position: 'absolute', top: '35%', right: 0, bottom: '22%', width: '18%', background: `rgba(${RGB}, 0.35)`, borderLeft: `1px dashed rgba(${RGB}, 0.9)` }} />
                <div style={{ position: 'absolute', left: 0, right: 0, top: 0, height: '8%', background: `rgba(${RGB}, 0.25)` }} />
              </div>
            )}
          </div>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 10, marginTop: 4, textAlign: 'center' }}>Reel 9:16</div>
        </div>
        <div>
          <div style={{ ...cadre, width: 110, height: 138 }} data-testid="v533-apercu-grille">
            <img src={src} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center', display: 'block' }} />
          </div>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: 10, marginTop: 4, textAlign: 'center' }}>Grille profil (recadrage centré)</div>
        </div>
      </div>
      {zonesSures && (
        <p style={{ color: 'rgba(255,255,255,0.45)', fontSize: 10, margin: '6px 0 0' }}>
          Zones teintées = bas de l'écran (légende, boutons) et colonne droite (actions sociales) : n'y placez rien d'important.
        </p>
      )}
    </div>
  );
}

export default function CampaignMediaUploader({
  mediaUrl = '',
  thumbnailUrl = '',
  thumbnailSource = null,
  thumbnailTime = null,
  onChange,          // ({ mediaUrl?, mediaFormat?, thumbnail_url?, thumbnail_source?, thumbnail_time? }) => void
  onBusyChange,      // (bool) => void : envoi en cours → « Suivant » bloqué par le parent
  onFormatDetected,  // (fmt) => void : '9:16' quand la vidéo est verticale
}) {
  const inputVideoRef = useRef(null);
  const inputImageRef = useRef(null);
  const videoRef = useRef(null);
  const abortRef = useRef(null);
  const dernierFichierRef = useRef(null);

  const [etat, setEtat] = useState('idle');       // idle | uploading | done | processing | error | cancelled
  const [pct, setPct] = useState(0);
  const [fichier, setFichier] = useState(null);   // { name, size, type }
  const [erreur, setErreur] = useState('');
  const [duree, setDuree] = useState(0);
  const [dimensions, setDimensions] = useState(null); // { w, h }
  const [curseur, setCurseur] = useState(0);      // secondes
  const [captureEnCours, setCaptureEnCours] = useState(false);
  const [zonesSures, setZonesSures] = useState(false);
  // Recadrage 9:16 (react-easy-crop)
  const [cropSrc, setCropSrc] = useState('');
  const [cropOrigine, setCropOrigine] = useState(null); // 'upload' | 'video_frame'
  const [cropTemps, setCropTemps] = useState(null);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [cropPixels, setCropPixels] = useState(null);
  const [miniatureEnvoi, setMiniatureEnvoi] = useState(false);

  useEffect(() => { if (onBusyChange) onBusyChange(etat === 'uploading' || etat === 'processing' || miniatureEnvoi); },
    [etat, miniatureEnvoi, onBusyChange]);
  useEffect(() => () => { if (abortRef.current) abortRef.current.abort(); }, []);

  const emettre = (patch) => { if (onChange) onChange(patch); };

  // ---------- ENVOI VIDÉO ----------
  const envoyer = async (file) => {
    if (!file) return;
    dernierFichierRef.current = file;
    setFichier({ name: file.name, size: file.size, type: file.type });
    setErreur(''); setPct(0); setEtat('uploading'); setDuree(0); setDimensions(null);
    const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    abortRef.current = ctrl;
    try {
      const { url, resourceType } = await uploadToCloudinary(file, {
        folder: 'campaigns', maxSizeMB: 25, maxSizeMBVideo: 100,
        onProgress: (p) => { setPct(p); if (p >= 100) setEtat('processing'); },
        signal: ctrl ? ctrl.signal : undefined,
      });
      setPct(100); setEtat('done');
      // Nouvelle vidéo = l'ancienne miniature ne correspond plus.
      emettre({ mediaUrl: url, thumbnail_url: '', thumbnail_source: null, thumbnail_time: null, mediaType: resourceType === 'video' ? 'upload' : 'image' });
    } catch (e) {
      if (/annul/i.test(e && e.message)) { setEtat('cancelled'); setErreur(''); }
      else { setEtat('error'); setErreur((e && e.message) || "L'envoi a échoué."); }
    } finally {
      abortRef.current = null;
      if (inputVideoRef.current) inputVideoRef.current.value = '';
    }
  };
  const annuler = () => { if (abortRef.current) abortRef.current.abort(); };
  const reessayer = () => { if (dernierFichierRef.current) envoyer(dernierFichierRef.current); };
  const remplacer = () => { if (inputVideoRef.current) inputVideoRef.current.click(); };

  // ---------- MÉTADONNÉES VIDÉO ----------
  const onMeta = () => {
    const v = videoRef.current; if (!v) return;
    setDuree(v.duration || 0);
    const w = v.videoWidth, h = v.videoHeight;
    setDimensions({ w, h });
    if (estPortrait(w, h) && onFormatDetected) onFormatDetected('9:16');
  };
  const deplacerCurseur = (t) => {
    const v = videoRef.current; setCurseur(t);
    if (v && Number.isFinite(t)) { try { v.currentTime = t; } catch (e) { /* ignore */ } }
  };

  // ---------- MINIATURE : envoi du blob final ----------
  const envoyerMiniature = async (blob, source, temps) => {
    setMiniatureEnvoi(true); setErreur('');
    try {
      const file = new File([blob], 'miniature-reel.jpg', { type: 'image/jpeg' });
      const { url } = await uploadToCloudinary(file, { folder: 'campaigns', maxSizeMB: 25 });
      emettre({ thumbnail_url: url, thumbnail_source: source, thumbnail_time: source === 'video_frame' ? Math.round((temps || 0) * 10) / 10 : null });
    } catch (e) {
      setErreur("Miniature non enregistrée : " + ((e && e.message) || 'erreur'));
    } finally { setMiniatureEnvoi(false); }
  };

  // A) depuis la vidéo
  const capturerDepuisVideo = async () => {
    const v = videoRef.current; if (!v) return;
    setCaptureEnCours(true); setErreur('');
    try {
      await attendreFrame(v);
      const blob = await capturerFrame(v);
      if (!blob) { setErreur('Capture impossible sur cette vidéo (hébergement externe sans autorisation).'); return; }
      if (dejaNeufSeize(v.videoWidth, v.videoHeight)) { await envoyerMiniature(blob, 'video_frame', v.currentTime); return; }
      // Frame pas au 9:16 → recadrage
      setCropOrigine('video_frame'); setCropTemps(v.currentTime); setCrop({ x: 0, y: 0 }); setZoom(1);
      setCropSrc(URL.createObjectURL(blob));
    } finally { setCaptureEnCours(false); }
  };
  // B) import d'une image
  const importerImage = (e) => {
    const f = e.target.files && e.target.files[0];
    if (inputImageRef.current) inputImageRef.current.value = '';
    if (!f) return;
    if (!/^image\/(jpe?g|png|webp)$/i.test(f.type)) { setErreur('Format accepté : JPG, JPEG, PNG, WEBP.'); return; }
    setCropOrigine('upload'); setCropTemps(null); setCrop({ x: 0, y: 0 }); setZoom(1);
    setCropSrc(URL.createObjectURL(f));
  };
  const validerCrop = async () => {
    if (!cropSrc || !cropPixels) return;
    try {
      const blob = await recadrerImage(cropSrc, cropPixels);
      setCropSrc('');
      await envoyerMiniature(blob, cropOrigine, cropTemps);
    } catch (e) { setErreur('Recadrage impossible : ' + ((e && e.message) || 'erreur')); }
  };

  const enEnvoi = etat === 'uploading';
  const videoPrete = !!mediaUrl && estVideoUrl(mediaUrl) && (etat === 'done' || etat === 'idle');
  const boutonSecondaire = { background: 'transparent', border: `1px solid rgba(${RGB}, 0.5)`, color: '#fff', borderRadius: 8, padding: '7px 12px', fontSize: 12, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6 };
  const boutonPrimaire = { ...boutonSecondaire, background: COULEUR, border: 'none', fontWeight: 600 };

  return (
    <div data-testid="v533-media" data-etat={etat} style={{ display: 'grid', gap: 10 }}>
      <input ref={inputVideoRef} type="file" accept="video/*,image/*" style={{ display: 'none' }} tabIndex={-1} aria-hidden="true"
        data-testid="v533-input-video" onChange={(e) => envoyer(e.target.files && e.target.files[0])} />
      <input ref={inputImageRef} type="file" accept={TYPES_IMAGE} style={{ display: 'none' }} tabIndex={-1} aria-hidden="true"
        data-testid="v533-input-image" onChange={importerImage} />

      {/* --- Bloc fichier + état --- */}
      <div style={{ padding: 12, borderRadius: 12, background: 'rgba(255,255,255,0.05)', border: `1px solid rgba(${RGB}, 0.25)` }}>
        {fichier && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', color: '#fff', fontSize: 12, flexWrap: 'wrap' }} data-testid="v533-fichier">
            <SvgIcon name={/^video\//.test(fichier.type) ? 'video' : 'image'} size={14} />
            <span style={{ fontWeight: 600, wordBreak: 'break-all' }}>{fichier.name}</span>
            <span style={{ color: 'rgba(255,255,255,0.5)' }}>{tailleLisible(fichier.size)} · {fichier.type || 'type inconnu'}</span>
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: fichier ? 8 : 0 }}>
          {etat === 'done' && <SvgIcon name="check" size={14} color={COULEUR} />}
          {(etat === 'uploading' || etat === 'processing') && <SvgIcon name="loader" size={14} className="animate-spin" />}
          <span data-testid="v533-etat" style={{ color: etat === 'error' ? '#ef4444' : '#fff', fontSize: 12, fontWeight: 600 }}>
            {etat === 'idle' && videoPrete ? 'Vidéo prête' : libelleEtat(etat, pct)}{etat === 'error' && erreur ? ' — ' + erreur : ''}
          </span>
          <span data-testid="v533-pct" style={{ marginLeft: 'auto', color: 'rgba(255,255,255,0.6)', fontSize: 12, fontVariantNumeric: 'tabular-nums' }}>
            {enEnvoi ? pct + ' %' : ''}
          </span>
        </div>
        {(enEnvoi || etat === 'processing') && <div style={{ marginTop: 8 }}><Barre pct={pct} /></div>}
        <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
          {etat === 'idle' && (
            <button type="button" onClick={remplacer} style={videoPrete ? boutonSecondaire : boutonPrimaire} data-testid={videoPrete ? 'v533-remplacer' : 'v533-choisir'}>
              <SvgIcon name={videoPrete ? 'refresh' : 'upload'} size={13} />{videoPrete ? 'Remplacer la vidéo' : 'Choisir une vidéo'}
            </button>
          )}
          {enEnvoi && (
            <button type="button" onClick={annuler} style={boutonSecondaire} data-testid="v533-annuler">
              <SvgIcon name="x" size={13} />Annuler
            </button>
          )}
          {(etat === 'error' || etat === 'cancelled') && (
            <>
              <button type="button" onClick={reessayer} style={boutonPrimaire} data-testid="v533-reessayer">
                <SvgIcon name="refresh" size={13} />Réessayer
              </button>
              <button type="button" onClick={remplacer} style={boutonSecondaire}><SvgIcon name="upload" size={13} />Choisir un autre fichier</button>
            </>
          )}
          {etat === 'done' && (
            <button type="button" onClick={remplacer} style={boutonSecondaire} data-testid="v533-remplacer">
              <SvgIcon name="refresh" size={13} />Remplacer la vidéo
            </button>
          )}
        </div>
      </div>

      {/* --- Aperçu vidéo + miniature --- */}
      {videoPrete && (
        <div style={{ display: 'grid', gap: 10 }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
            <div style={{ width: 150, aspectRatio: '9 / 16', background: '#000', borderRadius: 10, overflow: 'hidden', border: `1px solid rgba(${RGB}, 0.3)`, flexShrink: 0 }}>
              <video ref={videoRef} src={mediaUrl} playsInline preload="metadata" muted crossOrigin="anonymous"
                onLoadedMetadata={onMeta} data-testid="v533-video"
                style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block', background: '#000' }} />
            </div>
            <div style={{ flex: 1, minWidth: 180, color: 'rgba(255,255,255,0.7)', fontSize: 12 }}>
              <div data-testid="v533-infos">
                {duree > 0 ? 'Durée ' + dureeLisible(duree) : 'Chargement des informations…'}
                {dimensions && dimensions.w ? ' · ' + dimensions.w + '×' + dimensions.h : ''}
              </div>
              {dimensions && estPortrait(dimensions.w, dimensions.h) && (
                <div data-testid="v533-format-reel" style={{ marginTop: 6, color: COULEUR, fontWeight: 600 }}>Vidéo verticale détectée → Reel / Story 9:16</div>
              )}
              <div style={{ marginTop: 10, fontWeight: 600, color: '#fff' }}>Miniature du Reel</div>
              <p style={{ margin: '4px 0 8px', color: 'rgba(255,255,255,0.45)', fontSize: 11 }}>
                Miniature de référence Afroboost : appliquée sur les réseaux qui l'acceptent (les connecteurs actuels ne la poussent pas automatiquement).
              </p>
              <div style={{ display: 'grid', gap: 6 }}>
                <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.6)' }}>Choisir dans la vidéo — {dureeLisible(curseur)}</label>
                <input type="range" min={0} max={Math.max(0.1, duree || 0.1)} step={0.1} value={Math.min(curseur, duree || 0)}
                  onChange={(e) => deplacerCurseur(Number(e.target.value))} data-testid="v533-curseur" disabled={!duree}
                  style={{ width: '100%', accentColor: COULEUR }} />
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <button type="button" onClick={capturerDepuisVideo} disabled={!duree || captureEnCours || miniatureEnvoi} style={boutonPrimaire} data-testid="v533-capturer">
                    <SvgIcon name="camera" size={13} />{captureEnCours || miniatureEnvoi ? 'Enregistrement…' : 'Utiliser cette image comme miniature'}
                  </button>
                  <button type="button" onClick={() => inputImageRef.current && inputImageRef.current.click()} disabled={miniatureEnvoi} style={boutonSecondaire} data-testid="v533-importer">
                    <SvgIcon name="image" size={13} />Importer une image
                  </button>
                </div>
              </div>
            </div>
          </div>
          {erreur && etat !== 'error' && <div role="alert" style={{ color: '#ef4444', fontSize: 12 }}>{erreur}</div>}
          {thumbnailUrl && (
            <div data-testid="v533-miniature" data-source={thumbnailSource || ''} data-temps={thumbnailTime == null ? '' : String(thumbnailTime)}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#fff', fontSize: 12 }}>
                <SvgIcon name="check" size={13} color={COULEUR} />
                Miniature enregistrée{thumbnailSource === 'video_frame' && thumbnailTime != null ? ' (image à ' + dureeLisible(thumbnailTime) + ')' : thumbnailSource === 'upload' ? ' (image importée)' : ''}
              </div>
              <ApercuCouverture src={thumbnailUrl} zonesSures={zonesSures} onToggleZones={() => setZonesSures((z) => !z)} />
              <div style={{ marginTop: 6, color: 'rgba(255,255,255,0.4)', fontSize: 10 }}>
                Couverture via connecteur : {Object.entries(COUVERTURE_CONNECTEUR).map(([k, v]) => k + ' ' + (v ? 'oui' : 'non')).join(' · ')}
              </div>
            </div>
          )}
        </div>
      )}

      {/* --- Recadrage 9:16 --- */}
      {cropSrc && (
        <div data-testid="v533-cropper" onClick={(e) => e.stopPropagation()}
          style={{ position: 'fixed', inset: 0, zIndex: 10001, background: '#000', display: 'flex', flexDirection: 'column' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <Cropper image={cropSrc} crop={crop} zoom={zoom} aspect={RATIO_REEL} minZoom={1} maxZoom={3}
              onCropChange={setCrop} onZoomChange={setZoom} onCropComplete={(_, px) => setCropPixels(px)} />
          </div>
          <div style={{ padding: 14, background: 'rgba(0,0,0,0.8)', display: 'grid', gap: 10 }}>
            <div style={{ color: '#fff', fontSize: 12, textAlign: 'center' }}>Cadre 9:16 — déplacez l'image, zoomez légèrement ; ce que vous voyez dans le cadre est la miniature finale.</div>
            <input type="range" min={1} max={3} step={0.01} value={zoom} onChange={(e) => setZoom(Number(e.target.value))} data-testid="v533-zoom" style={{ width: '100%', accentColor: COULEUR }} />
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
              <button type="button" onClick={() => setCropSrc('')} style={boutonSecondaire} data-testid="v533-crop-annuler"><SvgIcon name="x" size={13} />Annuler</button>
              <button type="button" onClick={validerCrop} style={boutonPrimaire} data-testid="v533-crop-valider"><SvgIcon name="check" size={13} />Utiliser cette image comme miniature</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

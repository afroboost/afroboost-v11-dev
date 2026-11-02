/**
 * V645.3 — « BANNIÈRE BOUTIQUE — ACCUEIL »
 *
 * Rubrique DISTINCTE de l'onglet (3) Médias du Wizard de l'offre T-shirt. Elle
 * configure la grande bannière de la section Boutique de l'accueil.
 *
 * INDÉPENDANCE STRICTE (demande de Bassi) : ce composant ne lit et n'écrit QUE
 * les champs `concept.home_shop_banner_url` / `home_shop_banner_type`. Il ne
 * touche JAMAIS aux médias de l'offre T-shirt (`form.videoUrl`, `form.images`,
 * `form.thumbnail`). Réciproquement, enregistrer l'offre T-shirt ne passe PAS
 * par ici : les deux médias sont totalement séparés, dans les deux sens.
 *
 * RÉUTILISE l'éditeur média existant `VideoTrimEditor` (aucun nouvel éditeur) :
 * import photo/vidéo, aperçu, découpe (début/fin), lecture, capture de
 * miniature. L'upload passe par le même `uploadToCloudinary` que le reste du
 * dashboard.
 *
 * PERSISTANCE (vérifiée sur `update_concept`, server.py) :
 *  - IMAGE (y compris une frame capturée) → entièrement persistée (url + type).
 *  - VIDÉO : url + type persistés. La DÉCOUPE (début/fin) et la miniature d'une
 *    vidéo ne sont PAS encore stockables (champs concept absents ; `ConceptUpdate`
 *    est strict et ignore tout champ inconnu). Elles restent donc des réglages
 *    d'aperçu tant que les champs backend ne sont pas ajoutés — modification
 *    minimale soumise au GO de Bassi (home_shop_banner_trim_start/_end,
 *    home_shop_banner_thumbnail). Rien n'est inventé ni prétendu persistant.
 */
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import VideoTrimEditor from '../VideoTrimEditor';
import CloudinaryUploadButton, { uploadToCloudinary } from '../CloudinaryUploadButton';
import { analyserMediaUrl } from '../../utils/mediaOffre';

const PINK = 'var(--primary-color, #D91CD2)';
const BORD = '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.22)';

export default function BanniereBoutiqueSection({ API }) {
  const [url, setUrl] = useState('');
  const [type, setType] = useState('');          // 'image' | 'video' | ''
  const [trimStart, setTrimStart] = useState(null);
  const [trimEnd, setTrimEnd] = useState(null);
  const [thumb, setThumb] = useState('');
  const [chargement, setChargement] = useState(true);
  const [etat, setEtat] = useState('');          // '' | 'envoi' | 'ok' | message d'erreur
  const [sale, setSale] = useState(false);       // des changements non enregistrés ?

  // Lecture de la bannière actuelle (indépendante de l'offre).
  useEffect(() => {
    let vivant = true;
    (async () => {
      try {
        const r = await axios.get(`${API}/concept`);
        const c = (r && r.data) || {};
        if (!vivant) return;
        setUrl(c.home_shop_banner_url || '');
        setType(c.home_shop_banner_type || '');
        // V645.3c — restaurer la découpe (si un extrait valide est enregistré :
        // fin > début) et la miniature. Rétrocompatible : des champs absents
        // (ancienne bannière) → aucune découpe, pas de poster.
        const ts = Number(c.home_shop_banner_trim_start || 0);
        const te = Number(c.home_shop_banner_trim_end || 0);
        if (te > ts) { setTrimStart(ts); setTrimEnd(te); } else { setTrimStart(null); setTrimEnd(null); }
        if (c.home_shop_banner_type === 'video') setThumb(c.home_shop_banner_thumbnail || '');
        else if (c.home_shop_banner_type === 'image') setThumb(c.home_shop_banner_url || '');
        else setThumb('');
      } catch (e) {
        /* lecture impossible : on part d'une bannière vide, sans bloquer. */
      } finally {
        if (vivant) setChargement(false);
      }
    })();
    return () => { vivant = false; };
  }, [API]);

  const surImport = (nouvelleUrl, meta) => {
    // Type fiable : `resourceType` fourni par CloudinaryUploadButton
    // ('image' | 'video') ; repli sur l'analyse de l'URL si absent.
    const rt = meta && meta.resourceType;
    const t = rt === 'video' ? 'video'
      : rt === 'image' ? 'image'
      : ((analyserMediaUrl(nouvelleUrl || '') || {}).type === 'video' ? 'video' : 'image');
    setUrl(nouvelleUrl || '');
    setType(nouvelleUrl ? t : '');
    setTrimStart(null);
    setTrimEnd(null);
    setThumb(t === 'image' ? (nouvelleUrl || '') : '');
    setEtat('');
    setSale(true);
  };

  // Capture d'une frame de la vidéo = miniature (aperçu). Envoyée au stockage
  // média existant ; sa persistance définitive attend les champs backend (GO).
  const capturerMiniature = async (blob, apercuLocal) => {
    setThumb(apercuLocal);
    try {
      const f = new File([blob], 'banniere-' + Date.now() + '.jpg', { type: 'image/jpeg' });
      const r = await uploadToCloudinary(f, { folder: 'concept/banniere' });
      if (r && r.url) setThumb(r.url);
    } catch (e) {
      /* on garde l'aperçu local si l'envoi échoue. */
    }
  };

  const enregistrer = async () => {
    setEtat('envoi');
    try {
      // V645.3c — persistance complète. IMAGE : url + type (découpe/poster vidés).
      // VIDÉO : url + type + découpe (début/fin, 0/0 si pas d'extrait) + miniature.
      // Les nombres sont toujours envoyés (jamais null) pour passer le filtre
      // `is not None` de update_concept ; 0/0 signifie « pas de découpe ».
      const estVideo = !!url && type === 'video';
      await axios.put(`${API}/concept`, {
        home_shop_banner_url: url || '',
        home_shop_banner_type: url ? type : '',
        home_shop_banner_trim_start: estVideo ? Number(trimStart || 0) : 0,
        home_shop_banner_trim_end: estVideo ? Number(trimEnd || 0) : 0,
        home_shop_banner_thumbnail: estVideo ? (thumb || '') : '',
      });
      setSale(false);
      setEtat('ok');
      setTimeout(() => setEtat((e) => (e === 'ok' ? '' : e)), 2500);
    } catch (e) {
      const d = e && e.response && e.response.data && e.response.data.detail;
      setEtat(typeof d === 'string' ? d : 'Enregistrement impossible.');
    }
  };

  const retirer = async () => {
    setEtat('envoi');
    try {
      // V645.3c — retirer la bannière ET ses réglages (découpe + miniature).
      await axios.put(`${API}/concept`, {
        home_shop_banner_url: '', home_shop_banner_type: '',
        home_shop_banner_trim_start: 0, home_shop_banner_trim_end: 0, home_shop_banner_thumbnail: '',
      });
      setUrl(''); setType(''); setThumb(''); setTrimStart(null); setTrimEnd(null);
      setSale(false);
      setEtat('ok');
      setTimeout(() => setEtat((e) => (e === 'ok' ? '' : e)), 2500);
    } catch (e) {
      setEtat('Suppression impossible.');
    }
  };

  return (
    <div
      data-testid="banniere-boutique-section"
      style={{
        marginTop: 20, padding: 16, borderRadius: 12,
        border: BORD, background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.04)',
      }}
    >
      <h4 style={{ margin: 0, color: '#fff', fontSize: 15, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={PINK} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 15l5-5 4 4 3-3 6 6" /><circle cx="9" cy="9" r="1.5" />
        </svg>
        Bannière Boutique — Accueil
      </h4>
      <p style={{ margin: '8px 0 14px', color: 'rgba(255,255,255,0.6)', fontSize: 12.5, lineHeight: 1.5 }}>
        Grande bannière de la section Boutique de l'accueil (badge « AFROBOOST COLLECTION », titre « PORTE LE MOUVEMENT »).
        <strong style={{ color: 'rgba(255,255,255,0.78)' }}> Média indépendant du T-shirt </strong>
        : le modifier ne change pas les photos du produit, et inversement.
      </p>

      {chargement ? (
        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13 }}>Chargement…</p>
      ) : (
        <>
          {/* Import photo OU vidéo (même bouton d'upload que le reste du dashboard). */}
          <div style={{ marginBottom: 12 }}>
            <CloudinaryUploadButton
              accept="image/*,video/*"
              folder="concept/banniere"
              onUpload={surImport}
              data-testid="banniere-boutique-upload"
            />
          </div>

          {/* Aperçu : VideoTrimEditor pour une vidéo (découpe + miniature),
              image simple pour une photo. */}
          {url && type === 'video' ? (
            <div data-testid="banniere-boutique-apercu-video">
              <VideoTrimEditor
                videoUrl={url}
                trimStart={trimStart}
                trimEnd={trimEnd}
                aspectRatio="auto"
                thumbnail={thumb}
                hauteurMax="260px"
                libelleCapture="Capturer cette image comme miniature"
                onTrimChange={(t) => { setTrimStart(t ? t.start : null); setTrimEnd(t ? t.end : null); setSale(true); }}
                onThumbnailCapture={capturerMiniature}
              />
              <p style={{ margin: '8px 0 0', color: 'rgba(255,255,255,0.45)', fontSize: 11.5, lineHeight: 1.45 }}>
                La découpe (début/fin) et la miniature sont enregistrées : l'accueil
                lit le segment choisi en boucle, sans son, avec la miniature en poster.
              </p>
            </div>
          ) : url ? (
            <div
              data-testid="banniere-boutique-apercu-image"
              style={{ position: 'relative', width: '100%', aspectRatio: '16 / 7', borderRadius: 10, overflow: 'hidden', background: '#0c0c0e' }}
            >
              <img src={url} alt="Aperçu bannière Boutique" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            </div>
          ) : (
            <div
              style={{
                width: '100%', aspectRatio: '16 / 7', borderRadius: 10,
                border: '1px dashed rgba(255,255,255,0.18)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: 'rgba(255,255,255,0.4)', fontSize: 13, textAlign: 'center', padding: 16,
              }}
            >
              Aucune bannière configurée — l'accueil affiche un fond dégradé discret.
            </div>
          )}

          {/* Actions : Enregistrer / Retirer. */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14, flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={enregistrer}
              disabled={etat === 'envoi' || !sale}
              data-testid="banniere-boutique-enregistrer"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 7,
                padding: '9px 16px', borderRadius: 999, border: 'none',
                background: PINK, color: '#fff', fontSize: 13.5, fontWeight: 700,
                opacity: (etat === 'envoi' || !sale) ? 0.6 : 1,
                cursor: (etat === 'envoi' || !sale) ? 'default' : 'pointer',
              }}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" /><polyline points="17 21 17 13 7 13 7 21" /><polyline points="7 3 7 8 15 8" />
              </svg>
              Enregistrer la bannière
            </button>
            {url && (
              <button
                type="button"
                onClick={retirer}
                disabled={etat === 'envoi'}
                data-testid="banniere-boutique-retirer"
                style={{
                  padding: '9px 14px', borderRadius: 999,
                  border: '1px solid rgba(255,255,255,0.18)', background: 'transparent',
                  color: 'rgba(255,255,255,0.7)', fontSize: 13, fontWeight: 600, cursor: 'pointer',
                }}
              >
                Retirer la bannière
              </button>
            )}
            {etat === 'ok' && (
              <span data-testid="banniere-boutique-etat-ok" style={{ color: PINK, fontSize: 12.5, fontWeight: 600 }}>
                Bannière enregistrée.
              </span>
            )}
            {etat && etat !== 'ok' && etat !== 'envoi' && (
              <span style={{ color: 'var(--danger-color, #f87171)', fontSize: 12.5 }}>{etat}</span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

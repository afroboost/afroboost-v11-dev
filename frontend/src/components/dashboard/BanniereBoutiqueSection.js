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
import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import Cropper from 'react-easy-crop';
import VideoTrimEditor from '../VideoTrimEditor';
import CloudinaryUploadButton, { uploadToCloudinary } from '../CloudinaryUploadButton';
import { analyserMediaUrl } from '../../utils/mediaOffre';
import { CIBLES_BANNIERE } from '../../utils/banniereChamps';
import {
  CADRAGE_NEUTRE, cadrageNormalise, cadrageEstNeutre, styleCadrage, ancrageDepuisAire,
} from '../../utils/banniereCadrage';

const PINK = 'var(--primary-color, #D91CD2)';
const BORD = '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.22)';

/* V645.4k — cadrage : logique partagée avec le rendu de l'accueil, pour que
   l'aperçu montre exactement ce que verra le visiteur. `react-easy-crop` est
   déjà utilisé ailleurs dans le dashboard et gère nativement la vidéo. */
const RATIO_BANNIERE = 16 / 7;
const ERREUR_MINIATURE = "L'enregistrement de la miniature a échoué. La précédente est conservée. Réessayez.";

export default function BanniereBoutiqueSection({ API, cible = 'accueil' }) {
  // V646 : l'éditeur officiel et unique sert deux bannières. Tout passe par le
  // préfixe de la cible : aucune donnée n'est partagée entre elles.
  const config = CIBLES_BANNIERE[cible] || CIBLES_BANNIERE.accueil;
  const { prefixe, testid: tid } = config;
  // V646 : « Restaurer le média précédent », repris de l'ancien éditeur.
  const [precedent, setPrecedent] = useState(null);
  const [url, setUrl] = useState('');
  const [type, setType] = useState('');          // 'image' | 'video' | ''
  const [trimStart, setTrimStart] = useState(null);
  const [trimEnd, setTrimEnd] = useState(null);
  const [thumb, setThumb] = useState('');
  const [chargement, setChargement] = useState(true);
  const [etat, setEtat] = useState('');          // '' | 'envoi' | 'ok' | message d'erreur
  const [sale, setSale] = useState(false);       // des changements non enregistrés ?
  const [uploadMiniEnCours, setUploadMiniEnCours] = useState(false); // FIX 2 — garde anti-blob:
  // V646 : du clic sur « Capturer » à la réception de l'URL, aucune sauvegarde possible.
  const [captureMiniEnCours, setCaptureMiniEnCours] = useState(false);
  const miniOccupee = captureMiniEnCours || uploadMiniEnCours;
  // V646 : une miniature arrivée après un changement de média ne s'applique pas au nouveau.
  const generationMedia = useRef(0);
  const [erreurMini, setErreurMini] = useState('');                   // erreur upload miniature
  // V645.4k — cadrage enregistré + état de l'éditeur de cadrage.
  const [cadrage, setCadrage] = useState(CADRAGE_NEUTRE);
  const [cadrageOuvert, setCadrageOuvert] = useState(false);
  const [posCrop, setPosCrop] = useState({ x: 0, y: 0 });
  const [zoomCrop, setZoomCrop] = useState(1);
  const [aireCrop, setAireCrop] = useState(null);

  // Lecture de la bannière actuelle (indépendante de l'offre).
  useEffect(() => {
    let vivant = true;
    (async () => {
      try {
        const r = await axios.get(`${API}/concept`);
        const c = (r && r.data) || {};
        if (!vivant) return;
        setUrl(c[`${prefixe}_url`] || '');
        setType(c[`${prefixe}_type`] || '');
        // V645.3c — restaurer la découpe (si un extrait valide est enregistré :
        // fin > début) et la miniature. Rétrocompatible : des champs absents
        // (ancienne bannière) → aucune découpe, pas de poster.
        const ts = Number(c[`${prefixe}_trim_start`] || 0);
        const te = Number(c[`${prefixe}_trim_end`] || 0);
        if (te > ts) { setTrimStart(ts); setTrimEnd(te); } else { setTrimStart(null); setTrimEnd(null); }
        if (c[`${prefixe}_type`] === 'video') setThumb(c[`${prefixe}_thumbnail`] || '');
        else if (c[`${prefixe}_type`] === 'image') setThumb(c[`${prefixe}_url`] || '');
        else setThumb('');
        // V645.4k — cadrage relu ; absent (ancienne bannière) = cadrage neutre.
        setCadrage(cadrageNormalise(c[`${prefixe}_crop`]));
      } catch (e) {
        /* lecture impossible : on part d'une bannière vide, sans bloquer. */
      } finally {
        if (vivant) setChargement(false);
      }
    })();
    return () => { vivant = false; };
  }, [API, prefixe]);

  const memoriserPrecedent = () => {
    if (url) setPrecedent({ url, type, trimStart, trimEnd, thumb: (thumb || '').startsWith('blob:') ? '' : thumb, cadrage });
  };
  const restaurerPrecedent = () => {
    if (!precedent) return;
    generationMedia.current += 1;
    setUrl(precedent.url); setType(precedent.type);
    setTrimStart(precedent.trimStart); setTrimEnd(precedent.trimEnd);
    setThumb(precedent.thumb); setCadrage(precedent.cadrage);
    setPrecedent(null);
    setEtat('');
    setSale(true);
  };

  const surImport = (nouvelleUrl, meta) => {
    generationMedia.current += 1;
    memoriserPrecedent();
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
    // Un nouveau média repart d'un cadrage neutre : garder l'ancien cadrerait
    // au hasard dans une image qui n'a plus rien à voir.
    setCadrage(CADRAGE_NEUTRE);
    setEtat('');
    setSale(true);
  };

  // V645.4k — éditeur de cadrage : ouverture, validation, remise à zéro.
  const ouvrirCadrage = () => {
    setPosCrop({ x: 0, y: 0 });
    setZoomCrop(cadrage.zoom || 1);
    setAireCrop(null);
    setCadrageOuvert(true);
  };
  const validerCadrage = () => {
    // Sans mouvement, `onCropComplete` a tout de même été appelé au montage :
    // en l'absence d'aire on ne garde que le zoom, le centre reste au milieu.
    setCadrage(aireCrop ? ancrageDepuisAire(aireCrop, zoomCrop) : cadrageNormalise({ ...CADRAGE_NEUTRE, zoom: zoomCrop }));
    setCadrageOuvert(false);
    setSale(true);
  };
  const reinitCadrage = () => {
    setCadrage(CADRAGE_NEUTRE);
    setSale(true);
  };

  // Capture d'une frame de la vidéo = miniature.
  const capturerMiniature = async (blob, apercuLocal) => {
    if (uploadMiniEnCours) return;    // V646 : un envoi à la fois, la miniature valide reste connue
    const generation = generationMedia.current;
    const prevThumb = thumb;          // sauvegarder l'ancienne miniature valide
    setThumb(apercuLocal);            // aperçu immédiat (blob: temporaire)
    setSale(true);                    // FIX 1 — capture seule rend le formulaire modifié
    setUploadMiniEnCours(true);       // FIX 2 — bloquer Enregistrer le temps de l'envoi
    setErreurMini('');
    try {
      const f = new File([blob], 'banniere-' + Date.now() + '.jpg', { type: 'image/jpeg' });
      const r = await uploadToCloudinary(f, { folder: 'concept/banniere' });
      if (generation !== generationMedia.current) return;
      if (r && r.url) {
        setThumb(r.url);
      } else {
        // Réponse sans URL → on restaure et on signale.
        setThumb(prevThumb);
        setErreurMini(ERREUR_MINIATURE);
      }
    } catch (e) {
      // FIX 2 — échec réseau : on restaure l'ancienne miniature valide.
      if (generation === generationMedia.current) {
        setThumb(prevThumb);
        setErreurMini(ERREUR_MINIATURE);
      }
    } finally {
      setUploadMiniEnCours(false);
    }
  };

  const enregistrer = async () => {
    if (miniOccupee) return;  // sécurité (le bouton est déjà désactivé)
    // V646 : jamais d'URL temporaire en base, ni de miniature vidée par accident.
    if ((thumb || '').startsWith('blob:')) { setEtat(ERREUR_MINIATURE); return; }
    setEtat('envoi');
    try {
      // V645.3c — persistance complète.
      const thumbSure = thumb || '';
      const estVideo = !!url && type === 'video';
      await axios.put(`${API}/concept`, {
        [`${prefixe}_url`]: url || '',
        [`${prefixe}_type`]: url ? type : '',
        [`${prefixe}_trim_start`]: estVideo ? Number(trimStart || 0) : 0,
        [`${prefixe}_trim_end`]: estVideo ? Number(trimEnd || 0) : 0,
        [`${prefixe}_thumbnail`]: estVideo ? thumbSure : '',
        // V645.4k — toujours envoyé : un cadrage neutre est la façon d'EFFACER
        // un cadrage, `null` étant filtré avant d'atteindre la base.
        [`${prefixe}_crop`]: url ? cadrageNormalise(cadrage) : { ...CADRAGE_NEUTRE },
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
    if (miniOccupee) return;
    generationMedia.current += 1;
    setEtat('envoi');
    try {
      // V645.3c — retirer la bannière ET ses réglages (découpe + miniature).
      await axios.put(`${API}/concept`, {
        [`${prefixe}_url`]: '', [`${prefixe}_type`]: '',
        [`${prefixe}_trim_start`]: 0, [`${prefixe}_trim_end`]: 0, [`${prefixe}_thumbnail`]: '',
        [`${prefixe}_crop`]: { ...CADRAGE_NEUTRE },
      });
      memoriserPrecedent();
      setUrl(''); setType(''); setThumb(''); setTrimStart(null); setTrimEnd(null);
      setCadrage(CADRAGE_NEUTRE);
      setSale(false);
      setEtat('ok');
      setTimeout(() => setEtat((e) => (e === 'ok' ? '' : e)), 2500);
    } catch (e) {
      setEtat('Suppression impossible.');
    }
  };

  return (
    <details
      data-testid={`${tid}-section`}
      style={{
        marginTop: 20, padding: 16, borderRadius: 12,
        border: BORD, background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.04)',
      }}
    >
      {/* V646 : repliée par défaut, deux bannières ne doivent pas allonger l'écran. */}
      <summary data-testid={`${tid}-titre`} style={{ cursor: 'pointer', color: '#fff' }}>
      <h4 style={{ display: 'inline-flex', margin: 0, color: '#fff', fontSize: 15, fontWeight: 700, alignItems: 'center', gap: 8 }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={PINK} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 15l5-5 4 4 3-3 6 6" /><circle cx="9" cy="9" r="1.5" />
        </svg>
        {config.titre}
      </h4>
      </summary>
      <p style={{ margin: '8px 0 14px', color: 'rgba(255,255,255,0.6)', fontSize: 12.5, lineHeight: 1.5 }}>
        {config.description}
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
              maxSizeMB={25}
              maxSizeMBVideo={100}
              onUpload={surImport}
              data-testid={`${tid}-upload`}
            />
          </div>

          {/* Aperçu : VideoTrimEditor pour une vidéo (découpe + miniature),
              image simple pour une photo. */}
          {url && type === 'video' ? (
            <div data-testid={`${tid}-apercu-video`}>
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
                onCaptureEnCours={setCaptureMiniEnCours}
              />
              <p style={{ margin: '8px 0 0', color: 'rgba(255,255,255,0.45)', fontSize: 11.5, lineHeight: 1.45 }}>
                La découpe (début/fin) et la miniature sont enregistrées : {config.lieu} lit
                le segment choisi en boucle, sans son, avec la miniature en poster.
              </p>
            </div>
          ) : url ? (
            <div
              data-testid={`${tid}-apercu-image`}
              style={{ position: 'relative', width: '100%', aspectRatio: '16 / 7', borderRadius: 10, overflow: 'hidden', background: '#0c0c0e' }}
            >
              {/* L'aperçu applique le MÊME cadrage que l'accueil : ce qu'on voit
                  ici est ce qui sera rendu. */}
              <img
                src={url}
                alt="Aperçu bannière Boutique"
                data-testid={`${tid}-apercu-img`}
                style={{ width: '100%', height: '100%', ...styleCadrage(cadrage) }}
              />
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
              Aucune bannière configurée — {config.lieu} affiche un fond dégradé discret.
            </div>
          )}

          {/* V645.4k — Cadrage : recadrer / réinitialiser. Même cadrage pour
              une image et une vidéo, appliqué à l'affichage et non au fichier. */}
          {url && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12, flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={ouvrirCadrage}
                data-testid={`${tid}-cadrer`}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 7,
                  padding: '8px 14px', borderRadius: 999,
                  border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.5)',
                  background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.08)',
                  color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer',
                }}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M6 2v14a2 2 0 0 0 2 2h14" /><path d="M18 22V8a2 2 0 0 0-2-2H2" />
                </svg>
                Recadrer la bannière
              </button>
              {!cadrageEstNeutre(cadrage) && (
                <>
                  <span data-testid={`${tid}-cadrage-resume`} style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12 }}>
                    Zoom ×{cadrage.zoom.toFixed(2)} · ancrage {Math.round(cadrage.x * 100)} % / {Math.round(cadrage.y * 100)} %
                  </span>
                  <button
                    type="button"
                    onClick={reinitCadrage}
                    data-testid={`${tid}-cadrage-reinit`}
                    style={{
                      padding: '7px 12px', borderRadius: 999,
                      border: '1px solid rgba(255,255,255,0.18)', background: 'transparent',
                      color: 'rgba(255,255,255,0.7)', fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
                    }}
                  >
                    Réinitialiser le cadrage
                  </button>
                </>
              )}
            </div>
          )}

          {precedent && (
            <button
              type="button"
              onClick={restaurerPrecedent}
              disabled={miniOccupee}
              data-testid={`${tid}-restaurer`}
              style={{
                marginTop: 10, padding: '7px 12px', borderRadius: 999,
                border: '1px solid rgba(255,255,255,0.18)', background: 'transparent',
                color: 'rgba(255,255,255,0.8)', fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
              }}
            >
              Restaurer le média précédent
            </button>
          )}

          {/* Actions : Enregistrer / Retirer. */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14, flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={enregistrer}
              disabled={etat === 'envoi' || !sale || miniOccupee}
              data-testid={`${tid}-enregistrer`}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 7,
                padding: '9px 16px', borderRadius: 999, border: 'none',
                background: PINK, color: '#fff', fontSize: 13.5, fontWeight: 700,
                opacity: (etat === 'envoi' || !sale || miniOccupee) ? 0.6 : 1,
                cursor: (etat === 'envoi' || !sale || miniOccupee) ? 'default' : 'pointer',
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
                disabled={etat === 'envoi' || miniOccupee}
                data-testid={`${tid}-retirer`}
                style={{
                  padding: '9px 14px', borderRadius: 999,
                  border: '1px solid rgba(255,255,255,0.18)', background: 'transparent',
                  color: 'rgba(255,255,255,0.7)', fontSize: 13, fontWeight: 600, cursor: 'pointer',
                }}
              >
                Retirer la bannière
              </button>
            )}
            {miniOccupee && (
              <span data-testid={`${tid}-mini-envoi`} style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12.5 }}>
                Enregistrement de la miniature...
              </span>
            )}
            {erreurMini && !miniOccupee && (
              <span data-testid={`${tid}-mini-erreur`} style={{ color: 'var(--danger-color, #f87171)', fontSize: 12.5 }}>{erreurMini}</span>
            )}
            {etat === 'ok' && (
              <span data-testid={`${tid}-etat-ok`} style={{ color: PINK, fontSize: 12.5, fontWeight: 600 }}>
                Bannière enregistrée.
              </span>
            )}
            {etat && etat !== 'ok' && etat !== 'envoi' && (
              <span style={{ color: 'var(--danger-color, #f87171)', fontSize: 12.5 }}>{etat}</span>
            )}
          </div>

          {/* V645.4k — ÉDITEUR DE CADRAGE. Déplacement au doigt/souris et zoom,
              sur image comme sur vidéo. Rien n'est écrit tant que « Valider »
              n'a pas été pressé, puis « Enregistrer » persiste le tout. */}
          {cadrageOuvert && (
            <div
              data-testid={`${tid}-cadrage`}
              style={{
                position: 'fixed', inset: 0, zIndex: 10050,
                background: 'rgba(0,0,0,0.92)', display: 'flex', flexDirection: 'column',
              }}
            >
              <p style={{ margin: 0, padding: '14px 18px 10px', color: '#fff', fontSize: 14, fontWeight: 700 }}>
                Cadrer la bannière
                <span style={{ display: 'block', marginTop: 3, color: 'rgba(255,255,255,0.55)', fontSize: 12, fontWeight: 400 }}>
                  Fais glisser pour déplacer, règle le zoom ci-dessous.
                </span>
              </p>
              <div style={{ position: 'relative', flex: 1, minHeight: 0 }}>
                <Cropper
                  {...(type === 'video' ? { video: url } : { image: url })}
                  crop={posCrop}
                  zoom={zoomCrop}
                  aspect={RATIO_BANNIERE}
                  minZoom={1}
                  maxZoom={3}
                  restrictPosition
                  onCropChange={setPosCrop}
                  onZoomChange={setZoomCrop}
                  onCropComplete={(aire) => setAireCrop(aire)}
                />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 18px', flexWrap: 'wrap' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 9, flex: '1 1 220px', color: 'rgba(255,255,255,0.7)', fontSize: 12.5 }}>
                  Zoom
                  <input
                    type="range"
                    min={1}
                    max={3}
                    step={0.01}
                    value={zoomCrop}
                    onChange={(e) => setZoomCrop(Number(e.target.value))}
                    data-testid={`${tid}-cadrage-zoom`}
                    style={{ flex: 1, accentColor: PINK }}
                  />
                </label>
                <button
                  type="button"
                  onClick={() => setCadrageOuvert(false)}
                  data-testid={`${tid}-cadrage-annuler`}
                  style={{
                    padding: '9px 16px', borderRadius: 999,
                    border: '1px solid rgba(255,255,255,0.2)', background: 'transparent',
                    color: 'rgba(255,255,255,0.75)', fontSize: 13, fontWeight: 600, cursor: 'pointer',
                  }}
                >
                  Annuler
                </button>
                <button
                  type="button"
                  onClick={validerCadrage}
                  data-testid={`${tid}-cadrage-valider`}
                  style={{
                    padding: '9px 18px', borderRadius: 999, border: 'none',
                    background: PINK, color: '#fff', fontSize: 13.5, fontWeight: 700, cursor: 'pointer',
                  }}
                >
                  Valider le cadrage
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </details>
  );
}

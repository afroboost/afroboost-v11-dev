// V229 — Upload direct navigateur -> Cloudinary (preset unsigned).
//
// POURQUOI
// Jusqu'ici les coachs devaient coller une URL pour chaque visuel. Le seul
// upload existant (ConceptEditor -> `POST /coach/upload-asset`) stocke le
// fichier en base et plafonne a 4 Mo — le code lui-meme conseillait « pour les
// videos, utilisez un lien YouTube ». En passant par Cloudinary, le fichier ne
// transite plus par le backend : la limite monte a 100 Mo et le media est servi
// par un CDN au lieu de MongoDB.
//
// SECURITE
// Le `cloud name` et le `upload preset` sont PUBLICS par conception : un preset
// « unsigned » existe precisement pour etre expose au navigateur. Aucun secret
// (API key / API secret) n'apparait ici, et aucune signature n'est calculee
// cote client. C'est le mode d'emploi officiel de Cloudinary pour l'upload
// direct depuis un front.
//
// BUILD
// `process.env.REACT_APP_*` est inline par CRA AU MOMENT DU BUILD, pas au
// runtime. Ces deux variables doivent donc exister pendant `npx craco build` —
// voir les `ARG`/`ENV` du Dockerfile a la racine. Une variable posee uniquement
// comme variable d'execution Coolify n'atteindrait JAMAIS le bundle, et ce
// composant se rendrait `null` sans la moindre erreur visible.

import React, { useRef, useState } from 'react';
import SvgIcon from './SvgIcon';

// === V414 : LES ENVOIS VONT SUR NOTRE SERVEUR, PLUS SUR CLOUDINARY ===
//
// Le compte Cloudinary `dtm0r7hwq` est DESACTIVE : toute requete d'envoi y
// repond `401 — cloud_name dtm0r7hwq is disabled`. Chaque photo et chaque video
// deposee depuis le dashboard echouait donc, et les 23 medias deja heberges la
// sont devenus inaccessibles d'un coup.
//
// On envoie desormais vers `/api/coach/upload-asset`, qui range le fichier sur
// le DISQUE du serveur (V413) et renvoie une URL `/api/files/...` servie par
// nous — sans compte tiers, sans quota, sans desactivation possible.
//
// LE NOM DU FICHIER ET DES FONCTIONS EST CONSERVE A DESSEIN : six ecrans les
// importent (ConceptEditor, OffersManager, OfferWizard, BrandingManager,
// CampaignModal, Publications). Renommer aurait multiplie les points de
// rupture pour un gain cosmetique ; seul l'INTERIEUR change.
const API_BASE = (process.env.REACT_APP_BACKEND_URL || '') + '/api';

// Limites du serveur (`/coach/upload-asset`) : les refleter ici permet de
// prevenir l'utilisateur AVANT l'envoi plutot que de lui renvoyer un 400 sec.
// V415 : relevees en meme temps que celles du serveur (la contrainte des 16 Mo
// par document MongoDB a disparu avec le passage au disque). Ces valeurs
// DOIVENT rester alignees sur `max_sizes` d'api/server.py.
const PLAFONDS_MO = { image: 25, video: 100, logo: 5, audio: 50 };

/** Type d'asset attendu par le serveur, deduit du fichier. */
function typeAsset(file) {
  const mime = (file && file.type) || '';
  if (mime.indexOf('video/') === 0) return 'video';
  if (mime.indexOf('audio/') === 0) return 'audio';
  return 'image';
}

/**
 * V414 — identite du coach pour l'en-tete `X-User-Email`.
 * On reproduit la logique de l'intercepteur global d'App.js : ce composant
 * utilise `fetch`, qui ne passe PAS par les intercepteurs axios.
 */
function emailCoach() {
  try {
    const brut = localStorage.getItem('afroboost_coach_user');
    if (brut) {
      const parse = JSON.parse(brut);
      if (parse && parse.email) return String(parse.email).toLowerCase().trim();
    }
  } catch (e) { /* ignore */ }
  try {
    const idBrut = localStorage.getItem('afroboost_identity') || localStorage.getItem('af_chat_client');
    if (idBrut) {
      const id = JSON.parse(idBrut);
      if (id && id.email) return String(id.email).toLowerCase().trim();
    }
  } catch (e) { /* ignore */ }
  try {
    return (localStorage.getItem('afroboost_admin_persist') || '').toLowerCase().trim();
  } catch (e) { return ''; }
}

/**
 * V414 — l'envoi est desormais TOUJOURS disponible : il ne depend plus d'une
 * configuration externe, seulement de notre propre serveur. Le nom est conserve
 * parce que ConceptEditor s'en sert pour decider d'afficher le bouton.
 */
export function isCloudinaryConfigured() {
  return true;
}

/** V420 — un POST simple, avec progression. XHR : `fetch` ne remonte pas l'avancement. */
function v420Poster(url, formData, email, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    xhr.setRequestHeader('X-User-Email', email);
    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(e.loaded, e.total);
      };
    }
    xhr.onload = () => {
      let d = {};
      try { d = JSON.parse(xhr.responseText); } catch (e) { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(d);
      else reject(new Error((d && d.detail) || `Echec de l'envoi (${xhr.status}).`));
    };
    xhr.onerror = () => reject(new Error("Connexion interrompue pendant l'envoi."));
    xhr.send(formData);
  });
}

/** V420 — envoi monobloc (petits fichiers). */
async function v420EnvoiSimple(file, asset, email, onProgress) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('asset_type', asset);
  return v420Poster(`${API_BASE}/coach/upload-asset`, fd, email,
    onProgress ? (l, t) => onProgress(Math.round((l / t) * 100)) : null);
}

/**
 * V420 — envoi PAR MORCEAUX de 4 Mo.
 *
 * La progression est calculee sur l'ENSEMBLE du fichier (morceaux deja envoyes
 * + avancement du morceau courant) : une barre qui repartirait de zero a chaque
 * morceau serait pire que pas de barre du tout.
 *
 * Chaque morceau est reessaye deux fois : sur un reseau mobile, une coupure
 * ponctuelle ne doit pas condamner un envoi de plusieurs minutes.
 */
async function v420EnvoiParMorceaux(file, asset, email, onProgress) {
  const TAILLE = 4 * 1024 * 1024;
  const total = Math.ceil(file.size / TAILLE);
  // Identifiant simple : le serveur s'en sert comme NOM DE DOSSIER et refuse
  // tout ce qui sort de [A-Za-z0-9_-].
  const uploadId = (Date.now().toString(36) + Math.random().toString(36).slice(2, 8))
    .replace(/[^A-Za-z0-9_-]/g, '');

  let reponse = {};
  for (let i = 0; i < total; i++) {
    const debut = i * TAILLE;
    const morceau = file.slice(debut, Math.min(debut + TAILLE, file.size));
    const fd = new FormData();
    fd.append('file', morceau, `part_${i}`);
    fd.append('upload_id', uploadId);
    fd.append('chunk_index', String(i));
    fd.append('total_chunks', String(total));
    fd.append('original_name', file.name || 'media');
    fd.append('content_type', file.type || 'application/octet-stream');
    fd.append('asset_type', asset);

    let derniere = null;
    for (let essai = 0; essai < 3; essai++) {
      try {
        reponse = await v420Poster(`${API_BASE}/coach/upload-chunk`, fd, email,
          onProgress ? (l) => {
            const fait = debut + l;
            onProgress(Math.min(99, Math.round((fait / file.size) * 100)));
          } : null);
        derniere = null;
        break;
      } catch (e) {
        derniere = e;
        // Un refus du serveur (taille, type) ne se reessaie pas : il se
        // reproduirait a l'identique. Seules les coupures reseau valent un essai.
        if (/trop volumineux|invalide|Email coach/i.test(e.message || '')) throw e;
        await new Promise((r) => setTimeout(r, 800 * (essai + 1)));
      }
    }
    if (derniere) throw derniere;
  }
  if (onProgress) onProgress(100);
  return reponse;
}

/**
 * V229 — Envoie un fichier a Cloudinary et renvoie l'URL CDN optimisee.
 *
 * Exporte separement du bouton pour que les ecrans qui ont DEJA leur propre
 * bouton d'upload (ConceptEditor) puissent basculer sur Cloudinary sans
 * heriter d'une seconde interface.
 *
 * @param {File} file
 * @param {{folder?: string, maxSizeMB?: number}} opts
 * @returns {Promise<{url: string, resourceType: string, originalUrl: string}>}
 * @throws {Error} message deja lisible par un humain (affichable tel quel)
 */
export async function uploadToCloudinary(file, opts = {}) {
  // `folder`, `maxSizeMB` et `maxSizeMBVideo` restent acceptes pour ne casser
  // aucun appelant, mais les plafonds reels sont ceux du SERVEUR : annoncer
  // 100 Mo alors qu'il en refuse 15 ne ferait que deplacer l'echec plus loin.
  const asset = typeAsset(file);
  const plafond = PLAFONDS_MO[asset] || 5;

  if (file.size > plafond * 1024 * 1024) {
    const mb = (file.size / 1024 / 1024).toFixed(1);
    const quoi = asset === 'video' ? 'une vidéo' : (asset === 'audio' ? 'un audio' : 'une image');
    throw new Error(`Fichier trop lourd (${mb} Mo, maximum ${plafond} Mo pour ${quoi}).`);
  }

  const email = emailCoach();
  if (!email) {
    throw new Error("Session non reconnue : reconnectez-vous pour envoyer un fichier.");
  }

  // === V420 : AU-DELA DE 8 Mo, ON ENVOIE PAR MORCEAUX ===
  //
  // Un envoi monobloc se heurte a DEUX murs, tous deux mesures en production sur
  // un fichier de 199,8 Mo :
  //   - Cloudflare -> 413 apres 1,5 Mo envoyes (limite de corps : 100 Mo) ;
  //   - origine    -> 499 apres 92 Mo et 60,4 s (delai d'environ 60 s).
  // Decoupe en morceaux de 4 Mo, chaque requete dure une seconde ou deux : elle
  // ne s'approche d'aucune des deux limites. C'est la seule voie fiable.
  const data = file.size > 8 * 1024 * 1024
    ? await v420EnvoiParMorceaux(file, asset, email, opts.onProgress)
    : await v420EnvoiSimple(file, asset, email, opts.onProgress);

  if (!data.url) {
    throw new Error("Réponse inattendue du serveur (URL absente).");
  }

  return {
    url: data.url,                        // /api/files/<id>/<nom>
    resourceType: asset === 'audio' ? 'raw' : asset,
    originalUrl: data.url
  };
}

// V414 : `buildOptimizedUrl` a ete RETIREE. Elle inserait `q_auto,f_auto` dans
// une URL Cloudinary — une transformation qui n'a aucun sens sur une URL
// `/api/files/...` servie par nous. La laisser en place aurait entretenu
// l'illusion qu'un traitement d'image subsiste.

/**
 * V229 — Bouton d'upload autonome, a poser A COTE d'un champ URL existant.
 *
 * Le champ URL n'est jamais retire : coller un lien reste possible partout, et
 * l'upload ne fait qu'ajouter un second chemin vers la meme valeur.
 *
 * @param {(url: string, meta: {resourceType: string}) => void} onUpload
 *        Appele avec l'URL CDN. `meta.resourceType` vaut 'image' | 'video' |
 *        'raw' — necessaire la ou le state distingue une image d'une video.
 */
export default function CloudinaryUploadButton({
  onUpload,
  accept = 'image/*',
  label = 'Uploader',
  maxSizeMB = 10,
  maxSizeMBVideo,
  folder = 'offers',
  'data-testid': dataTestId,
}) {
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  // V351 : retour de SUCCES. Sans lui, la seule chose que voyait l'utilisateur
  // apres un envoi reussi etait l'apercu — et comme l'apercu etait casse pour la
  // video, il en concluait que l'upload avait echoue. Il n'avait pas echoue.
  const [succes, setSucces] = useState('');

  const handleFile = async (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;

    setError('');
    setSucces('');
    setUploading(true);
    try {
      const { url, resourceType } = await uploadToCloudinary(file, { folder, maxSizeMB, maxSizeMBVideo });
      onUpload(url, { resourceType });
      setSucces(resourceType === 'video' ? 'Vidéo ajoutée' : 'Image ajoutée');
    } catch (err) {
      setError(err.message);
      console.error('[V229] Cloudinary upload:', err);
    } finally {
      setUploading(false);
      // Remise a zero : sans cela, re-selectionner LE MEME fichier ne declenche
      // aucun `change` et l'utilisateur croit que le bouton est casse.
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  // V229: sans configuration, on n'affiche rien plutot qu'un bouton qui
  // echouerait a chaque clic. Le champ URL voisin reste utilisable.
  if (!isCloudinaryConfigured()) return null;

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={handleFile}
        style={{ display: 'none' }}
        tabIndex={-1}
        aria-hidden="true"
      />
      <button
        type="button"
        onClick={() => inputRef.current && inputRef.current.click()}
        disabled={uploading}
        data-testid={dataTestId}
        title={`${label} (max ${maxSizeMB} Mo)`}
        style={{
          background: uploading ? '#333' : 'linear-gradient(135deg, var(--primary-color, #D91CD2), #FF2DAA)',
          border: 'none',
          borderRadius: '8px',
          color: '#fff',
          padding: '6px 12px',
          fontSize: '12px',
          fontWeight: 500,
          cursor: uploading ? 'wait' : 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          whiteSpace: 'nowrap',
          transition: 'opacity 0.2s',
          opacity: uploading ? 0.7 : 1,
        }}
      >
        {uploading ? (
          <>
            <SvgIcon name="loader" size={14} className="animate-spin" />
            Upload...
          </>
        ) : (
          <>
            <SvgIcon name="upload" size={14} />
            {label}
          </>
        )}
      </button>
      {error && (
        <span
          role="alert"
          style={{ color: '#FF2DAA', fontSize: '11px', maxWidth: '220px', lineHeight: 1.3 }}
        >
          {error}
        </span>
      )}
      {/* V351 : confirmation explicite du succes (l'erreur a la priorite). */}
      {!error && succes && (
        <span
          data-testid="upload-succes"
          style={{ color: 'var(--primary-color, #D91CD2)', fontSize: '11px', fontWeight: 600, lineHeight: 1.3 }}
        >
          {succes}
        </span>
      )}
    </span>
  );
}

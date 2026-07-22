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

const CLOUD_NAME = process.env.REACT_APP_CLOUDINARY_CLOUD_NAME;
const UPLOAD_PRESET = process.env.REACT_APP_CLOUDINARY_UPLOAD_PRESET;

/** V229 — true si le build embarque bien la configuration Cloudinary. */
export function isCloudinaryConfigured() {
  return Boolean(CLOUD_NAME && UPLOAD_PRESET);
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
  const { folder = 'offers', maxSizeMB = 10 } = opts;

  if (!isCloudinaryConfigured()) {
    throw new Error("Upload non configure. Collez un lien a la place.");
  }
  if (file.size > maxSizeMB * 1024 * 1024) {
    const mb = (file.size / 1024 / 1024).toFixed(1);
    throw new Error(`Fichier trop lourd (${mb} Mo, maximum ${maxSizeMB} Mo).`);
  }

  const formData = new FormData();
  formData.append('file', file);
  formData.append('upload_preset', UPLOAD_PRESET);
  formData.append('folder', folder);

  // `auto` laisse Cloudinary determiner image / video / raw d'apres le fichier.
  const res = await fetch(
    `https://api.cloudinary.com/v1_1/${CLOUD_NAME}/auto/upload`,
    { method: 'POST', body: formData }
  );

  const data = await res.json().catch(function () { return {}; });

  if (!res.ok) {
    // Cloudinary renvoie { error: { message } } — bien plus utile qu'un code
    // HTTP nu pour diagnostiquer un preset mal configure.
    throw new Error(data?.error?.message || `Echec de l'upload (${res.status}).`);
  }
  if (!data.secure_url) {
    throw new Error("Reponse inattendue de Cloudinary (URL absente).");
  }

  return {
    url: buildOptimizedUrl(data.secure_url, data.resource_type),
    resourceType: data.resource_type || 'image',
    originalUrl: data.secure_url
  };
}

/**
 * V229 — Insere `q_auto,f_auto` (qualite et format automatiques) dans l'URL.
 *
 * ATTENTION : ces transformations n'existent QUE pour les ressources `image` et
 * `video`. Un fichier classe `raw` par Cloudinary (PDF, zip, format inconnu)
 * recevrait une URL invalide et ne se chargerait plus du tout. On renvoie donc
 * l'URL brute dans ce cas.
 */
function buildOptimizedUrl(secureUrl, resourceType) {
  if (resourceType !== 'image' && resourceType !== 'video') return secureUrl;
  // `/upload/` apparait une seule fois dans une URL de livraison Cloudinary.
  return secureUrl.replace('/upload/', '/upload/q_auto,f_auto/');
}

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
  folder = 'offers',
  'data-testid': dataTestId,
}) {
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const handleFile = async (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;

    setError('');
    setUploading(true);
    try {
      const { url, resourceType } = await uploadToCloudinary(file, { folder, maxSizeMB });
      onUpload(url, { resourceType });
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
          background: uploading ? '#333' : 'linear-gradient(135deg, #D91CD2, #FF2DAA)',
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
    </span>
  );
}

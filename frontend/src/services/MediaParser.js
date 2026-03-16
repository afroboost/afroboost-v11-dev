/**
 * MediaParser.js - Service de transformation des liens médias
 * 
 * Transforme automatiquement les liens Google Drive et YouTube
 * en liens directement exploitables pour l'affichage dans le chat.
 * 
 * === FORMATS SUPPORTÉS ===
 * - Google Drive (images, vidéos)
 * - YouTube (vidéos)
 * - Liens directs (jpg, png, gif, mp4, webm)
 */

// === PATTERNS REGEX ===
// Fix v7.1: Support URLs YouTube avec parametres ?si= et autres
const YOUTUBE_PATTERNS = [
  /(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/,
  /youtube\.com\/embed\/([a-zA-Z0-9_-]{11})/,
  /youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})/
];

const GOOGLE_DRIVE_PATTERNS = [
  /drive\.google\.com\/file\/d\/([a-zA-Z0-9_-]+)/,
  /drive\.google\.com\/open\?id=([a-zA-Z0-9_-]+)/,
  /docs\.google\.com\/(?:uc|file)\/d\/([a-zA-Z0-9_-]+)/,
  // Support des dossiers partagés
  /drive\.google\.com\/drive\/folders\/([a-zA-Z0-9_-]+)/,
  /drive\.google\.com\/folderview\?id=([a-zA-Z0-9_-]+)/
];

// Pattern pour détecter si c'est un dossier (pas un fichier)
const GOOGLE_DRIVE_FOLDER_PATTERNS = [
  /drive\.google\.com\/drive\/folders\/([a-zA-Z0-9_-]+)/,
  /drive\.google\.com\/folderview\?id=([a-zA-Z0-9_-]+)/
];

const DIRECT_IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico'];
const DIRECT_VIDEO_EXTENSIONS = ['mp4', 'webm', 'ogg', 'mov', 'avi'];

// Patterns pour les hébergeurs d'images connus (URLs sans extension standard)
const IMAGE_HOSTING_PATTERNS = [
  /images\.unsplash\.com\//i,
  /i\.imgur\.com\//i,
  /imgur\.com\/[a-zA-Z0-9]+\.(jpg|png|gif)/i,
  /cloudinary\.com\/.*\/image\//i,
  /res\.cloudinary\.com\//i,
  /pbs\.twimg\.com\//i,
  /media\.giphy\.com\//i,
  /cdn\.pixabay\.com\//i,
  /upload\.wikimedia\.org\/.*\.(jpg|jpeg|png|gif|svg|webp)/i,
  /firebasestorage\.googleapis\.com\/.*\.(jpg|jpeg|png|gif|webp)/i,
  /storage\.googleapis\.com\/.*\.(jpg|jpeg|png|gif|webp)/i,
  /blob\.core\.windows\.net\/.*\.(jpg|jpeg|png|gif|webp)/i,
  /s3\.amazonaws\.com\/.*\.(jpg|jpeg|png|gif|webp)/i
];

/**
 * Analyse une URL et retourne les informations du média
 * @param {string} url - URL à analyser
 * @returns {object} - { type, directUrl, thumbnailUrl, embedUrl, videoId, platform }
 */
export const parseMediaUrl = (url) => {
  if (!url || typeof url !== 'string') {
    return { type: 'unknown', error: 'URL invalide' };
  }

  const trimmedUrl = url.trim();

  // === YOUTUBE ===
  for (const pattern of YOUTUBE_PATTERNS) {
    const match = trimmedUrl.match(pattern);
    if (match && match[1]) {
      const videoId = match[1];
      return {
        type: 'youtube',
        platform: 'youtube',
        videoId,
        directUrl: `https://www.youtube.com/watch?v=${videoId}`,
        embedUrl: `https://www.youtube-nocookie.com/embed/${videoId}?rel=0&modestbranding=1&showinfo=0&iv_load_policy=3`,
        thumbnailUrl: `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`,
        // Alternatives de miniatures
        thumbnails: {
          default: `https://img.youtube.com/vi/${videoId}/default.jpg`,
          medium: `https://img.youtube.com/vi/${videoId}/mqdefault.jpg`,
          high: `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`,
          max: `https://img.youtube.com/vi/${videoId}/maxresdefault.jpg`
        }
      };
    }
  }

  // === GOOGLE DRIVE ===
  // D'abord vérifier si c'est un dossier
  for (const pattern of GOOGLE_DRIVE_FOLDER_PATTERNS) {
    const match = trimmedUrl.match(pattern);
    if (match && match[1]) {
      const folderId = match[1];
      return {
        type: 'drive_folder',
        platform: 'google_drive',
        folderId,
        // Les dossiers ne peuvent pas être embedés directement
        directUrl: `https://drive.google.com/drive/folders/${folderId}`,
        thumbnailUrl: null, // Pas de miniature pour les dossiers
        // Lien pour ouvrir le dossier
        previewUrl: `https://drive.google.com/drive/folders/${folderId}`,
        embedUrl: null,
        isFolder: true
      };
    }
  }
  
  // Ensuite vérifier les fichiers
  for (const pattern of GOOGLE_DRIVE_PATTERNS) {
    // Skip les patterns de dossiers (déjà traités)
    if (GOOGLE_DRIVE_FOLDER_PATTERNS.some(fp => fp.source === pattern.source)) {
      continue;
    }
    const match = trimmedUrl.match(pattern);
    if (match && match[1]) {
      const fileId = match[1];
      return {
        type: 'drive',
        platform: 'google_drive',
        fileId,
        // Lien direct pour téléchargement/affichage
        directUrl: `https://lh3.googleusercontent.com/d/${fileId}=w1000`,
        // Miniature (peut ne pas fonctionner pour tous les fichiers)
        thumbnailUrl: `https://drive.google.com/thumbnail?id=${fileId}&sz=w400`,
        // Lien de prévisualisation dans Drive
        previewUrl: `https://drive.google.com/file/d/${fileId}/preview`,
        // Lien embed pour iframe
        embedUrl: `https://drive.google.com/file/d/${fileId}/preview`,
        isFolder: false
      };
    }
  }

  // === LIEN DIRECT IMAGE ===
  const extension = trimmedUrl.split('.').pop()?.toLowerCase().split('?')[0];
  if (DIRECT_IMAGE_EXTENSIONS.includes(extension)) {
    return {
      type: 'image',
      platform: 'direct',
      directUrl: trimmedUrl,
      thumbnailUrl: trimmedUrl
    };
  }

  // === LIEN DIRECT VIDÉO ===
  if (DIRECT_VIDEO_EXTENSIONS.includes(extension)) {
    return {
      type: 'video',
      platform: 'direct',
      directUrl: trimmedUrl,
      thumbnailUrl: null // Pas de miniature pour les vidéos directes
    };
  }

  // === HÉBERGEURS D'IMAGES CONNUS ===
  for (const pattern of IMAGE_HOSTING_PATTERNS) {
    if (pattern.test(trimmedUrl)) {
      return {
        type: 'image',
        platform: 'hosted_image',
        directUrl: trimmedUrl,
        thumbnailUrl: trimmedUrl
      };
    }
  }

  // === INCONNU ===
  return {
    type: 'link',
    platform: 'unknown',
    directUrl: trimmedUrl,
    thumbnailUrl: null
  };
};

/**
 * Vérifie si une URL est un média supporté
 * @param {string} url 
 * @returns {boolean}
 */
export const isMediaUrl = (url) => {
  const parsed = parseMediaUrl(url);
  return ['youtube', 'drive', 'image', 'video'].includes(parsed.type);
};

/**
 * Génère une miniature pour n'importe quel type de média
 * @param {string} url 
 * @returns {string|null}
 */
export const getMediaThumbnail = (url) => {
  const parsed = parseMediaUrl(url);
  return parsed.thumbnailUrl || null;
};

/**
 * Génère l'URL embed pour iframe (YouTube, Drive)
 * @param {string} url 
 * @returns {string|null}
 */
export const getEmbedUrl = (url) => {
  const parsed = parseMediaUrl(url);
  return parsed.embedUrl || null;
};

/**
 * Détecte le type de média à partir de l'URL
 * @param {string} url 
 * @returns {string} - 'youtube' | 'drive' | 'image' | 'video' | 'link'
 */
export const getMediaType = (url) => {
  const parsed = parseMediaUrl(url);
  return parsed.type;
};

/**
 * Transforme un lien Google Drive de partage en lien direct
 * @param {string} shareUrl - Lien de partage Google Drive
 * @returns {string|null} - Lien direct ou null si invalide
 */
export const driveShareToDirectUrl = (shareUrl) => {
  const parsed = parseMediaUrl(shareUrl);
  if (parsed.platform === 'google_drive') {
    return parsed.directUrl;
  }
  return null;
};

/**
 * Extrait l'ID d'une vidéo YouTube
 * @param {string} url 
 * @returns {string|null}
 */
export const extractYouTubeId = (url) => {
  const parsed = parseMediaUrl(url);
  if (parsed.platform === 'youtube') {
    return parsed.videoId;
  }
  return null;
};

// Export par défaut
export default {
  parseMediaUrl,
  isMediaUrl,
  getMediaThumbnail,
  getEmbedUrl,
  getMediaType,
  driveShareToDirectUrl,
  extractYouTubeId
};

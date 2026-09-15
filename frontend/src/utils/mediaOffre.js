/**
 * MÉDIAS D'UNE OFFRE — une seule règle de lecture pour la vitrine, la fiche,
 * les cartes et la prévisualisation du dashboard.
 *
 * Les documents d'offre portent trois champs historiques : `thumbnail`,
 * `images[]` (max 5) et `videoUrl`. Le champ « vidéo » accepte AUSSI une image
 * (V229 : « visuel de couverture animé ou fixe ») — en production, plusieurs
 * offres ont un .png dans `videoUrl`. Un lecteur qui suppose « videoUrl =
 * vidéo » rend alors une zone vide : c'était le bug des cartes aimants.
 *
 * Règle :
 *  - POSTER (image fixe) : la miniature dédiée d'abord (`thumbnail`), puis les
 *    images, puis le champ vidéo s'il contient une image ;
 *  - VIDÉO : le champ vidéo d'abord, puis les images, puis la miniature si elle
 *    contient une vidéo (cas Pulse : miniature = .mp4).
 */

const EXT_VIDEO = ['.mp4', '.webm', '.mov', '.avi', '.m4v', '.ogv'];
const EXT_IMAGE = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp', '.ico'];
const CDN_IMAGE = ['imgbb.com', 'cloudinary.com', 'imgur.com', 'unsplash.com', 'pexels.com', 'i.ibb.co'];

/**
 * Le type d'une URL de média — YouTube / Vimeo (id), fichier vidéo, image.
 * C'est l'ancien `parseMediaUrl` d'App.js, déplacé ici pour être partagé.
 */
export function analyserMediaUrl(url) {
  if (!url || typeof url !== 'string') return null;
  const trimmedUrl = url.trim();
  if (!trimmedUrl) return null;

  const ytMatch = trimmedUrl.match(/(?:youtube\.com\/(?:watch\?v=|embed\/|v\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
  if (ytMatch) return { type: 'youtube', id: ytMatch[1] };

  const vimeoMatch = trimmedUrl.match(/vimeo\.com\/(?:video\/)?(\d+)/);
  if (vimeoMatch) return { type: 'vimeo', id: vimeoMatch[1] };

  const lowerUrl = trimmedUrl.toLowerCase();
  // V224 : l'extension n'est reconnue qu'en FIN de chemin, avant `?` ou `#`.
  const lowerPath = lowerUrl.split('#')[0].split('?')[0];
  if (EXT_VIDEO.some((ext) => lowerPath.endsWith(ext))) return { type: 'video', url: trimmedUrl };

  // V233 : Cloudinary video — /video/upload/ dans le chemin, sans extension.
  if (lowerUrl.includes('cloudinary.com') && lowerUrl.includes('/video/upload/')) return { type: 'video', url: trimmedUrl };

  if (EXT_IMAGE.some((ext) => lowerUrl.includes(ext)) || CDN_IMAGE.some((cdn) => lowerUrl.includes(cdn))) {
    return { type: 'image', url: trimmedUrl };
  }
  // Par défaut : une image (beaucoup de CDN n'ont pas d'extension).
  return { type: 'image', url: trimmedUrl };
}

const candidats = (offre) => {
  const o = offre || {};
  const images = Array.isArray(o.images) ? o.images : [];
  return { thumbnail: o.thumbnail || '', images, videoUrl: o.videoUrl || '' };
};

const premier = (liste, type, analyser) => {
  for (let i = 0; i < liste.length; i += 1) {
    const m = analyser(liste[i]);
    if (m && m.type === type) return m.url;
  }
  return '';
};

/**
 * { poster, video } — l'image fixe à afficher (miniature dédiée prioritaire)
 * et la vidéo lisible, s'il y en a une. `analyser` = analyserMediaUrl par
 * défaut (injectable pour les bancs).
 */
export function mediaPrincipal(offre, analyser) {
  const a = typeof analyser === 'function' ? analyser : analyserMediaUrl;
  const c = candidats(offre);
  const poster = premier([c.thumbnail, ...c.images, c.videoUrl].filter(Boolean), 'image', a);
  const video = premier([c.videoUrl, ...c.images, c.thumbnail].filter(Boolean), 'video', a);
  return { poster, video };
}

/** Vrai si le champ « vidéo » de l'offre contient en réalité une image. */
export function champVideoEstImage(offre, analyser) {
  const a = typeof analyser === 'function' ? analyser : analyserMediaUrl;
  const m = a((offre || {}).videoUrl || '');
  return !!(m && m.type === 'image');
}

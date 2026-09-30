/**
 * V565 — LECTURE DU MÉDIA DE L'« AFFICHE ÉVÉNEMENT » (ConceptEditor), extraite du
 * popup d'accueil (App.js, EventPosterModal) pour que la vitrine ET l'espace
 * abonné lisent la même URL de la même façon. Fonctions pures.
 */

const VIDEO_DIRECTE = /\.(mp4|webm|mov|m4v|ogv)(\?|#|$)/i;

/** 'embed' (YouTube / Vimeo), 'video' (fichier vidéo direct) ou 'image'. */
export function typeMediaAffiche(url) {
  const u = String(url || '').toLowerCase();
  if (u.includes('youtube.com') || u.includes('youtu.be') || u.includes('vimeo.com')) return 'embed';
  if (VIDEO_DIRECTE.test(u)) return 'video';
  return 'image';
}

/** L'URL du lecteur intégré (muet, en lecture auto), ou null. Ne lève jamais. */
export function urlEmbedAffiche(url) {
  const m = String(url || '');
  try {
    if (m.includes('youtu.be')) {
      const id = m.split('/').pop().split('?')[0];
      return `https://www.youtube.com/embed/${id}?autoplay=1&mute=1`;
    }
    if (m.includes('youtube.com')) {
      const id = new URLSearchParams(new URL(m).search).get('v');
      return `https://www.youtube.com/embed/${id}?autoplay=1&mute=1`;
    }
    if (m.includes('vimeo.com')) {
      const id = m.split('/').pop();
      return `https://player.vimeo.com/video/${id}?autoplay=1&muted=1`;
    }
  } catch (e) {
    return null;
  }
  return null;
}

/** Libellé d'un bouton : champ jamais renseigné -> défaut ; vide -> bouton masqué (V258). */
export function libelleBoutonAffiche(valeur, defaut) {
  return valeur === undefined || valeur === null ? defaut : String(valeur);
}

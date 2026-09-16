/**
 * V533 — Miniature du Reel : règles PURES (testables sans DOM lourd).
 *
 * Utilisé par le dashboard campagnes (CampaignMediaUploader). Aucune règle
 * métier nouvelle côté serveur : la miniature est une RÉFÉRENCE Afroboost
 * (`thumbnail_url`), appliquée sur les réseaux qui l'acceptent.
 */

export const RATIO_REEL = 9 / 16;

/** Une vidéo est « verticale » (Reel / Story) si sa hauteur dépasse nettement sa largeur. */
export function estPortrait(largeur, hauteur) {
  const w = Number(largeur) || 0, h = Number(hauteur) || 0;
  if (!w || !h) return false;
  return h / w >= 1.2;
}

/** Une image est déjà au ratio 9:16 (tolérance 2 %) : pas besoin de recadrer. */
export function dejaNeufSeize(largeur, hauteur) {
  const w = Number(largeur) || 0, h = Number(hauteur) || 0;
  if (!w || !h) return false;
  return Math.abs(w / h - RATIO_REEL) / RATIO_REEL <= 0.02;
}

/** « 12,4 Mo » / « 830 Ko » — jamais un nombre brut d'octets à l'écran. */
export function tailleLisible(octets) {
  const n = Number(octets) || 0;
  if (n >= 1024 * 1024) return (n / 1024 / 1024).toFixed(1).replace('.', ',') + ' Mo';
  if (n >= 1024) return Math.round(n / 1024) + ' Ko';
  return n + ' o';
}

/** « 0:32 » depuis des secondes. */
export function dureeLisible(sec) {
  const s = Math.max(0, Math.round(Number(sec) || 0));
  return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
}

/**
 * Libellé d'état de l'envoi — une seule source de vérité pour l'écran ET les tests.
 * etat ∈ idle | uploading | done | processing | error | cancelled
 */
export function libelleEtat(etat, pct) {
  switch (etat) {
    case 'uploading': return 'Envoi de la vidéo… ' + Math.max(0, Math.min(100, Math.round(pct || 0))) + ' %';
    case 'done': return 'Vidéo envoyée';
    case 'processing': return 'Traitement de la vidéo…';
    case 'error': return "L'envoi a échoué";
    case 'cancelled': return 'Envoi annulé';
    default: return 'Choisir une vidéo';
  }
}

/**
 * Zone de recadrage 9:16 CENTRÉE par défaut sur une image de (w×h) pixels —
 * ce que l'utilisateur voit avant de déplacer/zoomer. Renvoie {x,y,width,height}.
 */
export function cadreNeufSeizeCentre(largeur, hauteur) {
  const w = Number(largeur) || 0, h = Number(hauteur) || 0;
  if (!w || !h) return { x: 0, y: 0, width: 0, height: 0 };
  if (w / h > RATIO_REEL) {          // trop large (paysage / carré) : on garde toute la hauteur
    const cw = Math.round(h * RATIO_REEL);
    return { x: Math.round((w - cw) / 2), y: 0, width: cw, height: h };
  }
  const ch = Math.round(w / RATIO_REEL); // trop haut : on garde toute la largeur
  return { x: 0, y: Math.round((h - ch) / 2), width: w, height: ch };
}

/**
 * Recadre une image (URL/objectURL) sur `pixelCrop` {x,y,width,height} → Blob JPEG.
 * Même principe que le recadrage des publications (V268c), isolé ici pour ne
 * pas importer tout `Publications.js` dans le dashboard campagnes.
 */
export function recadrerImage(imageSrc, pixelCrop, qualite = 0.9) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.crossOrigin = 'anonymous';
    image.onload = () => {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(pixelCrop.width));
        canvas.height = Math.max(1, Math.round(pixelCrop.height));
        const ctx = canvas.getContext('2d');
        ctx.drawImage(image, pixelCrop.x, pixelCrop.y, pixelCrop.width, pixelCrop.height,
          0, 0, canvas.width, canvas.height);
        canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('canvas vide'))), 'image/jpeg', qualite);
      } catch (e) { reject(e); }
    };
    image.onerror = () => reject(new Error("Image illisible."));
    image.src = imageSrc;
  });
}

/**
 * Support de la COUVERTURE par le connecteur de publication.
 * Côté Afroboost il n'existe AUCUN connecteur social (le canal « instagram »
 * d'une campagne est marqué « Envoi manuel requis »). La miniature reste donc
 * une référence : l'écran ne doit jamais prétendre qu'elle sera appliquée
 * automatiquement partout.
 */
export const COUVERTURE_CONNECTEUR = Object.freeze({
  instagram: false,
  facebook: false,
  tiktok: false,
  youtube: false,
});

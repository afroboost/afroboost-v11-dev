/**
 * FORMAT D'AFFICHAGE VIDÉO — auto / 9:16 / 16:9 / 1:1.
 *
 * Une seule source de vérité pour : la valeur stockée sur l'offre
 * (`video_aspect_ratio`), la détection depuis les dimensions réelles d'un MP4
 * (videoWidth / videoHeight), et la boîte CSS qui rend la vidéo SANS jamais la
 * déformer (object-fit: contain, fond derrière). Le lecteur visiteur, la
 * prévisualisation admin et le plein écran consomment ces mêmes fonctions.
 */

export const RATIO_AUTO = 'auto';
export const RATIOS = [
  { valeur: 'auto', libelle: 'Auto', aide: 'Format d’origine de la vidéo' },
  { valeur: '9:16', libelle: 'Vertical 9:16', aide: 'Reel, story, téléphone' },
  { valeur: '16:9', libelle: 'Horizontal 16:9', aide: 'Paysage, YouTube' },
  { valeur: '1:1', libelle: 'Carré 1:1', aide: 'Post carré' },
];

export const ratioValide = (v) => RATIOS.some((r) => r.valeur === v);

export const normaliserRatio = (v) => (ratioValide(v) ? v : RATIO_AUTO);

/**
 * Le ratio déduit des dimensions RÉELLES. Tolérance : on classe par la
 * proportion, pas par des pixels exacts (1080×1920, 720×1280, 1088×1920… sont
 * tous du 9:16). Un 4:3 ou un 3:2 reste « auto » : on n'invente pas un cadre.
 */
export const ratioDepuisDimensions = (largeur, hauteur) => {
  const w = Number(largeur); const h = Number(hauteur);
  if (!(w > 0) || !(h > 0)) return RATIO_AUTO;
  const q = w / h;
  if (Math.abs(q - 1) <= 0.08) return '1:1';
  if (Math.abs(q - 9 / 16) <= 0.08) return '9:16';
  if (Math.abs(q - 16 / 9) <= 0.2) return '16:9';
  return RATIO_AUTO;
};

/** La valeur CSS `aspect-ratio` d'un ratio, ou '' pour auto. */
export const aspectCss = (ratio) => {
  switch (normaliserRatio(ratio)) {
    case '9:16': return '9 / 16';
    case '16:9': return '16 / 9';
    case '1:1': return '1 / 1';
    default: return '';
  }
};

export const estPortrait = (ratio, largeur, hauteur) => {
  const r = normaliserRatio(ratio);
  if (r === '9:16') return true;
  if (r === '16:9' || r === '1:1') return false;
  return Number(hauteur) > Number(largeur) && Number(largeur) > 0;
};

/**
 * Les styles du couple conteneur / <video> pour un rendu fidèle :
 *  - le conteneur porte le ratio (ou rien en auto), un fond, et centre ;
 *  - la vidéo est en `contain` : jamais étirée, jamais rognée.
 * `hauteurMax` borne la hauteur (ex. 60vh dans une fiche) ; un 9:16 se rend
 * alors en colonne centrée avec des bandes, un 16:9 en pleine largeur.
 */
export const stylesLecteur = (ratio, options = {}) => {
  const r = normaliserRatio(ratio);
  const hauteurMax = options.hauteurMax || '70vh';
  const fond = options.fond || 'var(--video-bg, #000)';
  const conteneur = {
    position: 'relative',
    width: '100%',
    background: fond,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
    maxHeight: hauteurMax,
  };
  const video = {
    display: 'block',
    objectFit: 'contain',
    objectPosition: 'center',
    background: fond,
    maxWidth: '100%',
    maxHeight: hauteurMax,
  };
  if (r === '9:16') {
    // Colonne centrée : hauteur = la borne, largeur déduite du ratio.
    video.height = hauteurMax;
    video.width = 'auto';
    video.aspectRatio = '9 / 16';
  } else if (r === '1:1') {
    video.width = 'auto';
    video.height = `min(${hauteurMax}, 100vw)`;
    video.aspectRatio = '1 / 1';
  } else if (r === '16:9') {
    video.width = '100%';
    video.height = 'auto';
    video.aspectRatio = '16 / 9';
  } else {
    // auto : le navigateur garde le ratio intrinsèque ; contain fait le reste.
    video.width = '100%';
    video.height = 'auto';
  }
  return { conteneur, video };
};

/** Libellé lisible des dimensions détectées : « 1080 × 1920 → 9:16 ». */
export const libelleDetection = (largeur, hauteur) => {
  const w = Number(largeur); const h = Number(hauteur);
  if (!(w > 0) || !(h > 0)) return '';
  const r = ratioDepuisDimensions(w, h);
  return `${w} × ${h} → ${r === RATIO_AUTO ? 'format libre' : r}`;
};

/**
 * V554 : heroEditeur.js — la logique NON visuelle de l'editeur visuel du Hero
 * (Dashboard > Video Hero). Fonctions PURES, testees par jest : l'ecran
 * (components/dashboard/HeroEditeurVisuel.js) ne fait que les appeler.
 *
 * Rappel du contrat (CONTRAT_HERO_V554) : la disposition est stockee dans
 * `concept.heroLayout`, en coordonnees NORMALISEES (centre de l'element,
 * fraction de la largeur / hauteur de la boite Hero). L'apercu rend la boite a
 * sa taille NATIVE puis la reduit par `transform: scale(echelle)` : toute
 * position lue a l'ecran doit donc etre divisee par l'echelle.
 */
import {
  HERO_TAILLE_MIN,
  HERO_TAILLE_MAX,
  borner,
  deplacer,
  layoutsEgaux,
  normaliserLayout,
} from './heroLayout';

// V554 : tailles simulees de la boite Hero (contrat) : fenetre 1440x900 ->
// boite 1440x387 ; fenetre 390x844 -> boite 390x473.
export const APERCU_DIMENSIONS = {
  desktop: { largeur: 1440, hauteur: 387 },
  mobile: { largeur: 390, hauteur: 473 },
};

// V554 : pas des fleches (1 % ; Maj = 5 %) et de la taille (0,1).
export const PAS_FLECHE = 0.01;
export const PAS_FLECHE_MAJ = 0.05;
export const PAS_TAILLE = 0.1;
// Distance (px ECRAN) sous laquelle un appui reste un simple clic de selection.
export const SEUIL_GLISSER_PX = 3;

const estNombre = (v) => typeof v === 'number' && Number.isFinite(v);
const dimensions = (appareil) => APERCU_DIMENSIONS[appareil === 'mobile' ? 'mobile' : 'desktop'];

// Echelle de l'apercu : la boite native doit tenir dans la largeur disponible,
// jamais agrandie au-dela de 1.
export function echelleApercu(largeurDispo, appareil) {
  const d = dimensions(appareil);
  if (!estNombre(largeurDispo) || largeurDispo <= 0) return 0;
  return Math.min(1, largeurDispo / d.largeur);
}

// Taille AFFICHEE du cadre (px ecran) : hauteur = hauteur native x echelle,
// aucun espace vide sous l'apercu.
export function tailleCadre(largeurDispo, appareil) {
  const d = dimensions(appareil);
  const e = echelleApercu(largeurDispo, appareil);
  return { echelle: e, largeur: Math.round(d.largeur * e * 100) / 100, hauteur: Math.round(d.hauteur * e * 100) / 100 };
}

// Point ecran -> px de la boite NATIVE (non mis a l'echelle).
export function ecranVersBoite(pointeur, rectBoite, echelle) {
  const e = echelle > 0 ? echelle : 1;
  return { x: (pointeur.x - rectBoite.left) / e, y: (pointeur.y - rectBoite.top) / e };
}

// Ecart (px natifs) entre le pointeur et le centre de l'element, memorise au
// pointerdown : l'element ne « saute » pas sous le doigt a la premiere prise.
export function ecartSaisie(pointeur, rectBoite, echelle, centreNormalise, largeurBoite, hauteurBoite) {
  const p = ecranVersBoite(pointeur, rectBoite, echelle);
  return { x: p.x - centreNormalise.x * largeurBoite, y: p.y - centreNormalise.y * hauteurBoite };
}

// Pointeur courant -> nouveau centre NORMALISE (non borne).
export function pointeurVersCentre(pointeur, rectBoite, echelle, ecart, largeurBoite, hauteurBoite) {
  const p = ecranVersBoite(pointeur, rectBoite, echelle);
  const e = ecart || { x: 0, y: 0 };
  return {
    x: largeurBoite > 0 ? (p.x - e.x) / largeurBoite : 0.5,
    y: hauteurBoite > 0 ? (p.y - e.y) / hauteurBoite : 0.5,
  };
}

// Au-dela du seuil, l'appui devient un glissement (sinon : simple selection).
export function aBougeAssez(depart, courant, seuil = SEUIL_GLISSER_PX) {
  if (!depart || !courant) return false;
  return Math.hypot(courant.x - depart.x, courant.y - depart.y) >= seuil;
}

// Pas d'une fleche : { dx, dy } normalises.
export function pasFleche(direction, maj) {
  const p = maj ? PAS_FLECHE_MAJ : PAS_FLECHE;
  switch (direction) {
    case 'haut': return { dx: 0, dy: -p };
    case 'bas': return { dx: 0, dy: p };
    case 'gauche': return { dx: -p, dy: 0 };
    case 'droite': return { dx: p, dy: 0 };
    default: return { dx: 0, dy: 0 };
  }
}

// Touche clavier -> direction (null = touche non geree).
export function directionDeTouche(cle) {
  return { ArrowUp: 'haut', ArrowDown: 'bas', ArrowLeft: 'gauche', ArrowRight: 'droite' }[cle] || null;
}

/**
 * Decale un element d'un pas de fleche, a partir de sa position AFFICHEE
 * (`positionsActuelles`, lues dans le DOM : en mode flux comme en mode
 * positionne, deja bornees) — jamais d'une valeur stockee hors zone qui ne
 * bougerait pas a l'ecran. `dims` (optionnel) = { largeurEl, hauteurEl,
 * largeurBoite, hauteurBoite } en px natifs : le resultat reste dans la zone sure.
 */
export function decaler(layout, appareil, el, direction, maj, positionsActuelles, dims) {
  const base = positionsActuelles && positionsActuelles[el];
  if (!base || !estNombre(base.x) || !estNombre(base.y)) return layout;
  const { dx, dy } = pasFleche(direction, maj);
  if (!dx && !dy) return layout;
  let pos = { x: base.x + dx, y: base.y + dy };
  if (dims && dims.largeurBoite > 0 && dims.hauteurBoite > 0) {
    pos = borner(pos, dims.largeurEl, dims.hauteurEl, dims.largeurBoite, dims.hauteurBoite, appareil);
  }
  return deplacer(layout, appareil, el, pos, positionsActuelles);
}

export function pourcentageTaille(size) {
  const s = estNombre(size) ? size : 1;
  return `${Math.round(s * 100)} %`;
}

export function peutReduire(size) {
  return (estNombre(size) ? size : 1) > HERO_TAILLE_MIN + 1e-9;
}

export function peutAgrandir(size) {
  return (estNombre(size) ? size : 1) < HERO_TAILLE_MAX - 1e-9;
}

// Forme ENVOYEE au PUT /api/concept : TOUJOURS un objet (une chaine / liste ->
// 422 -> tout l'auto-save echoue). « Aucune disposition » = les deux appareils null.
export function layoutPourEnvoi(layout) {
  return normaliserLayout(layout) || { v: 1, desktop: null, mobile: null };
}

/**
 * Decision au relachement : que faut-il ecrire dans le concept ?
 * - simple clic (pas de glissement) -> null (rien) ;
 * - disposition identique a celle de depart -> null (aucun setState identique) ;
 * - sinon le layout a envoyer (objet).
 */
export function layoutAEcrire(layoutInitial, layoutFinal, aGlisse) {
  if (!aGlisse || !layoutFinal) return null;
  if (layoutsEgaux(layoutInitial, layoutFinal)) return null;
  return layoutPourEnvoi(layoutFinal);
}

// ─── Media de l'apercu : le PREMIER media visible, comme le carrousel ───────
const RE_YOUTUBE = /(?:youtube\.com\/(?:watch\?v=|embed\/|v\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/;

function typeMedia(video) {
  const url = String((video && video.url) || '').toLowerCase();
  if (!url) return 'aucun';
  if (url.includes('youtube.com') || url.includes('youtu.be')) return 'youtube';
  if (url.includes('vimeo.com')) return 'vimeo';
  if (/\.(jpg|jpeg|png|webp|gif|svg|bmp)(\?|$)/i.test(url) || video.type === 'image' || url.includes('/image_')) return 'image';
  if (/\.(mp4|webm|mov|avi|mkv|m4v)(\?|$)/i.test(url) || video.type === 'upload' || video.type === 'video' || url.includes('/video_') || url.includes('/api/files/')) return 'video';
  return 'image'; // lien direct inconnu : tente comme image (l'echec laisse le fond noir)
}

function resoudreMedia(video) {
  const type = typeMedia(video);
  const url = video && video.url;
  if (type === 'youtube') {
    const m = String(url).match(RE_YOUTUBE);
    if (m) return { type: 'image', url: `https://img.youtube.com/vi/${m[1]}/hqdefault.jpg` };
    return video.thumbnail ? { type: 'image', url: video.thumbnail } : { type: 'aucun', url: '' };
  }
  if (type === 'vimeo') {
    return video.thumbnail ? { type: 'image', url: video.thumbnail } : { type: 'aucun', url: '' };
  }
  if (type === 'aucun') return { type: 'aucun', url: '' };
  return { type, url };
}

export function mediaApercu(concept) {
  const c = concept || {};
  const liste = Array.isArray(c.heroVideos) ? c.heroVideos.filter((v) => v && v.url && v.is_visible !== false) : [];
  if (liste.length > 0) return resoudreMedia(liste[0]);
  if (typeof c.heroImageUrl === 'string' && c.heroImageUrl.trim()) return resoudreMedia({ url: c.heroImageUrl.trim() });
  return { type: 'aucun', url: '' };
}

// Statut discret de l'auto-save (prop `conceptSaveStatus` du tableau de bord).
export function libelleStatut(status) {
  if (status === 'saving') return 'Enregistrement…';
  if (status === 'saved') return 'Enregistré';
  if (status === 'error') return "Erreur d'enregistrement";
  return '';
}

/**
 * V645.4k — CADRAGE DE LA BANNIÈRE BOUTIQUE.
 *
 * Le média de la bannière est rendu en `object-fit: cover` : le cadrage se
 * ramène donc à un point d'ancrage (`object-position`) et un zoom. On ne
 * recadre JAMAIS le fichier — un recadrage destructif interdirait de revenir
 * en arrière, et serait de toute façon impossible sur une vidéo sans
 * réencodage. Le même cadrage s'applique donc à l'image et à la vidéo.
 *
 * Partagé par l'éditeur (dashboard) et le rendu (accueil) pour que l'aperçu
 * montre EXACTEMENT ce que verra le visiteur.
 */

export const CADRAGE_NEUTRE = { x: 0.5, y: 0.5, zoom: 1 };

export function cadrageNormalise(brut) {
  const n = (v, dft) => {
    // `Number(null)` vaut 0 : sans ce garde, une valeur absente se changerait
    // en ancrage collé au bord au lieu de retomber sur le défaut.
    if (v === null || v === undefined || v === '') return dft;
    const x = Number(v);
    return Number.isFinite(x) ? x : dft;
  };
  if (!brut || typeof brut !== 'object') return { ...CADRAGE_NEUTRE };
  return {
    x: Math.min(Math.max(n(brut.x, 0.5), 0), 1),
    y: Math.min(Math.max(n(brut.y, 0.5), 0), 1),
    zoom: Math.min(Math.max(n(brut.zoom, 1), 1), 3),
  };
}

export function cadrageEstNeutre(c) {
  const v = cadrageNormalise(c);
  return v.x === 0.5 && v.y === 0.5 && v.zoom === 1;
}

/** Style à poser sur le <img> / <video>. Cadrage neutre = rendu d'origine. */
export function styleCadrage(c) {
  const v = cadrageNormalise(c);
  // `+(…).toFixed(2)` : deux décimales au plus, sans « 50.00% » inutile.
  const pct = (n) => `${+(n * 100).toFixed(2)}%`;
  const ancre = `${pct(v.x)} ${pct(v.y)}`;
  return {
    objectFit: 'cover',
    objectPosition: ancre,
    // Zoomer depuis le point d'ancrage : agrandir depuis le centre ferait
    // fuir la zone que le coach vient justement de choisir.
    ...(v.zoom !== 1 ? { transform: `scale(${v.zoom})`, transformOrigin: ancre } : {}),
  };
}

/**
 * `croppedArea` de react-easy-crop est en POURCENTAGES de l'image : il survit
 * au changement de résolution, contrairement aux pixels. On en déduit la
 * position relative de la fenêtre dans l'image, donc le point d'ancrage.
 */
export function ancrageDepuisAire(aire, zoom) {
  if (!aire) return cadrageNormalise({ ...CADRAGE_NEUTRE, zoom });
  const libreX = 100 - (Number(aire.width) || 100);
  const libreY = 100 - (Number(aire.height) || 100);
  return cadrageNormalise({
    x: libreX > 0.01 ? (Number(aire.x) || 0) / libreX : 0.5,
    y: libreY > 0.01 ? (Number(aire.y) || 0) / libreY : 0.5,
    zoom,
  });
}

/**
 * V646 — ROUTES DE LA PAGE BOUTIQUE. Fonctions pures, sans routeur : le projet
 * lit `window.location.pathname` à la main (cf. /espace, /parrainage).
 *
 * L'URL d'un produit porte son nom lisible ET le début de son identifiant :
 * `/boutique/t-shirt-1-cours-offert-84b7d8c6`. C'est l'identifiant qui décide :
 * renommer le produit ne casse donc aucun lien déjà partagé.
 */

/** `null` = hors boutique ; `''` = la liste ; sinon le segment du produit. */
export function lireRouteBoutique(chemin) {
  const m = String(chemin || '').match(/^\/boutique(?:\/([^/]+))?\/?$/);
  if (!m) return null;
  try {
    return m[1] ? decodeURIComponent(m[1]) : '';
  } catch (e) {
    return m[1];
  }
}

function courtId(produit) {
  return String((produit && produit.id) || '').slice(0, 8);
}

export function cheminProduit(produit) {
  const nom = String((produit && produit.name) || 'produit')
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  return `/boutique/${nom || 'produit'}-${courtId(produit)}`;
}

export function trouverProduit(produits, segment) {
  if (!segment) return null;
  return (produits || []).find((p) => {
    const court = courtId(p);
    return !!court && (p.id === segment || segment.endsWith(`-${court}`));
  }) || null;
}

/**
 * `?visitor=true` doit survivre à la navigation : c'est lui qui garde un coach
 * connecté sur la vitrine (« Vue visiteur ») au lieu de son tableau de bord.
 */
export function avecModeVisiteur(chemin, recherche) {
  return new URLSearchParams(recherche || '').get('visitor') === 'true'
    ? `${chemin}?visitor=true`
    : chemin;
}

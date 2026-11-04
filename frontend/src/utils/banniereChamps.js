/**
 * V646 — LES DEUX BANNIÈRES BOUTIQUE, UN SEUL ÉDITEUR.
 *
 * `BanniereBoutiqueSection` est l'éditeur officiel et unique. Il sert deux
 * cibles aux données STRICTEMENT séparées, chacune sous son préfixe de champs
 * dans `concept`. Rien n'est partagé : ni le média, ni la découpe, ni la
 * miniature, ni le cadrage.
 */
export const CIBLES_BANNIERE = {
  accueil: {
    prefixe: 'home_shop_banner',
    testid: 'banniere-boutique',
    titre: "Bannière Boutique — Accueil",
    description: "Grande bannière de la section Boutique de l'accueil.",
    lieu: "l'accueil",
  },
  boutique: {
    prefixe: 'boutique_page_banner',
    testid: 'banniere-page-boutique',
    titre: 'Bannière — Page Boutique',
    description: 'Grande bannière de la page /boutique. Indépendante de celle de l\'accueil.',
    lieu: 'la page Boutique',
  },
};

const PREFIXES = Object.values(CIBLES_BANNIERE).map((c) => c.prefixe + '_');

/**
 * Le concept à envoyer par l'enregistrement GÉNÉRAL du tableau de bord (autosave
 * et bouton), SANS aucun champ de bannière.
 *
 * POURQUOI : ces deux enregistrements envoient TOUT l'état `concept`, lu à
 * l'ouverture du tableau de bord. Une bannière modifiée entre-temps par l'éditeur
 * officiel aurait été réécrite avec ses anciennes valeurs au moindre changement
 * de logo ou de couleur. Le serveur ignore les champs absents (`ConceptUpdate`,
 * filtre `is not None`) : les retirer ici les préserve en base.
 */
export function conceptSansBannieres(concept) {
  const propre = {};
  Object.keys(concept || {}).forEach((cle) => {
    if (!PREFIXES.some((p) => cle.startsWith(p))) propre[cle] = concept[cle];
  });
  return propre;
}

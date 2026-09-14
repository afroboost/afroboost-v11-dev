/**
 * 📍 lieuOffre — LE lieu d'une offre. Une seule règle, pour tous les écrans.
 *
 * LE BUG QU'IL FERME. Le lieu s'écrivait à un endroit et se lisait à un autre.
 * L'admin « Mes offres » modifie `offer.location` ; la carte visiteur, elle,
 * affichait `linkedCourses[0].locationName` — le lieu du PREMIER cours lié — et
 * masquait explicitement `offer.location` dès qu'un cours lié en avait un.
 * Corriger l'offre ne changeait donc rien pour le visiteur, et le « premier »
 * cours lié n'est même pas un choix : c'est l'ordre de `linked_course_ids`.
 * Mesuré le 14/09/2026 sur « 🎁 Cours d'essai GRATUIT » : l'admin affichait
 * « Bord du Lac, Auvernier » pendant que l'accueil affichait
 * « Chem. des Valangines 97 », l'adresse d'un cours lié jamais remis à jour.
 *
 * LA RÈGLE, ET POURQUOI CELLE-CI. Ce que le coach écrit SUR L'OFFRE gagne.
 * C'est le seul champ qu'il voit quand il corrige un lieu, donc le seul dont il
 * peut attendre un effet. Le lieu d'un cours lié ne sert plus que de REPLI,
 * pour les offres qui n'ont pas de lieu propre — leur affichage ne change pas.
 *
 * Aucun composant ne relit ces champs directement : ils passent tous par ici,
 * sinon la divergence renaît au premier écran ajouté.
 */

/** Texte de lieu exploitable, ou '' — jamais `undefined`, jamais un espace. */
function texteLieu(valeur) {
  return typeof valeur === 'string' ? valeur.trim() : '';
}

/**
 * @param {object} offre  l'offre, éventuellement enrichie de `linkedCourses`.
 * @returns {{texte: string, source: 'offre'|'cours'|'aucun', cours: object|null}}
 */
export function lieuOffre(offre) {
  const o = offre || {};
  // 1) Le lieu propre de l'offre — celui que l'admin modifie.
  const propre = texteLieu(o.location) || texteLieu(o.location_address);
  if (propre) return { texte: propre, source: 'offre', cours: null };
  // 2) À défaut seulement : le premier cours lié qui porte un lieu.
  const cours = (Array.isArray(o.linkedCourses) ? o.linkedCourses : [])
    .find((c) => c && texteLieu(c.locationName)) || null;
  if (cours) return { texte: texteLieu(cours.locationName), source: 'cours', cours };
  return { texte: '', source: 'aucun', cours: null };
}

/**
 * Lien Maps du lieu affiché — dérivé de la MÊME résolution, jamais d'une autre.
 *
 * `mapsUrl` n'est retenu que s'il commence par http : ce champ est saisi au
 * dashboard, et une URL `javascript:` y passerait. Sinon on fabrique une
 * recherche sur le texte réellement affiché — pointer ailleurs que ce qui est
 * écrit serait pire que ne pas être cliquable.
 */
export function lienMapsLieu(offre) {
  const { texte, cours } = lieuOffre(offre);
  if (!texte) return null;
  const brut = cours && typeof cours.mapsUrl === 'string' ? cours.mapsUrl.trim() : '';
  if (/^https?:\/\//i.test(brut)) return brut;
  return 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(texte);
}

export default lieuOffre;

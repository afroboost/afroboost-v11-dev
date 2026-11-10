// V655 — UNE SEULE RÈGLE POUR OUVRIR LES FORMULES.
//
// Les formules s'ouvraient par `/?offres=toutes` : un paramètre, qui ne se dit
// pas au téléphone, ne s'écrit pas sur une affiche et ne s'indexe pas. `/offres`
// est la même porte avec une adresse partageable.
//
// La règle vit ICI, en fonction pure, pour deux raisons : elle se teste sans
// navigateur, et il n'en existe qu'UNE — `App.js` l'appelle, personne ne la
// réécrit. Les deux entrées restent valides : casser `/?offres=toutes` serait
// une régression silencieuse, ce paramètre étant écrit dans la page d'essai
// servie par le serveur et dans des liens déjà partagés.

/**
 * Faut-il ouvrir le panneau « toutes les formules » ?
 * @param {string} chemin   `window.location.pathname`
 * @param {string} recherche `window.location.search`
 */
export function ouvrirLesOffres(chemin, recherche) {
  return parParametre(recherche) || parChemin(chemin);
}

/** `/?offres=toutes` — la porte d'origine (V622), inchangée. */
export function parParametre(recherche) {
  try {
    return new URLSearchParams(recherche || '').get('offres') === 'toutes';
  } catch (e) {
    // Une recherche illisible ne doit jamais empêcher l'accueil de s'afficher.
    return false;
  }
}

/** `/offres`, avec ou sans barre finale, insensible à la casse. */
export function parChemin(chemin) {
  return /^\/offres\/?$/i.test(String(chemin || ''));
}

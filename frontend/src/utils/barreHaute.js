/**
 * V554 — LA BARRE HAUTE : ce qu'elle contient, décidé sans DOM.
 *
 * Deux occupants possibles : le compte à rebours d'une offre (« OFFRE
 * FONDATEURS ») et le bouton « Retour au dashboard » du mode Vue visiteur.
 * Avant V554 c'étaient deux éléments `fixed` indépendants qui se marchaient
 * dessus (z-index 40 contre 9999). Ils partagent maintenant UNE barre, et la
 * page réserve exactement sa hauteur mesurée (`--af-bandeau`).
 *
 * Fonctions pures : testées dans utils/__tests__/barreHaute.test.js.
 */

function pad2(n) { return n < 10 ? '0' + n : '' + n; }

/**
 * Découpe un nombre de secondes restantes en jours / heures / minutes / secondes
 * et produit le minuteur affiché. Toujours la même largeur de caractères
 * (« 00j 00h 00m 00s ») : combinée à `tabular-nums`, la barre ne « danse »
 * plus à chaque seconde.
 */
export function minuteurBarre(restantSecondes) {
  var r = Math.max(0, Math.floor(Number(restantSecondes) || 0));
  var d = Math.floor(r / 86400);
  var h = Math.floor((r % 86400) / 3600);
  var m = Math.floor((r % 3600) / 60);
  var s = r % 60;
  return pad2(d) + 'j ' + pad2(h) + 'h ' + pad2(m) + 'm ' + pad2(s) + 's';
}

/**
 * Ce que la barre doit montrer.
 *  - compteActif  : une offre a un compte à rebours ET il reste du temps
 *  - modeVisiteur : l'admin regarde sa vitrine en « Vue visiteur »
 * Rien des deux -> pas de barre du tout (0 px réservé).
 */
export function etatBarreHaute(entree) {
  var e = entree || {};
  var compte = !!e.compteActif;
  var retour = !!e.modeVisiteur;
  var disposition = compte && retour ? 'retour-compte' : compte ? 'compte' : retour ? 'retour' : null;
  return { visible: disposition !== null, compte: compte, retour: retour, disposition: disposition };
}

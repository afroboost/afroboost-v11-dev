/**
 * LE TYPE D'UN BLOC HORAIRE — recurrent, ou date unique.
 *
 * UNE OFFRE PORTE UNE LISTE DE BLOCS INDEPENDANTS (`linked_course_ids`), et
 * chaque bloc a SON type. « lundi chaque semaine », « mercredi chaque semaine »
 * et « samedi 29 aout » cohabitent dans la meme offre : c'est le modele qui
 * existe deja depuis V246, pas une invention.
 *
 * LE CONTRAT DE STOCKAGE NE BOUGE PAS. `date` non vide = ponctuel ; c'est ce
 * que lit `_v184_next_occurrences` (api/server.py). Aucune cle nouvelle,
 * aucune migration, aucun backfill.
 *
 * CE QUI MANQUAIT, ET QUI EST ICI. Le bouton « Date unique » posait `date: ''`
 * — or l'ecran ne revele le champ date que si `date` est NON VIDE. Cliquer sur
 * un bloc recurrent le laissait donc rigoureusement identique : le bouton
 * etait inerte, et aucun bloc ne pouvait devenir ponctuel. Il manquait un etat
 * D'ECRAN — « ce bloc passe en date unique, la date n'est pas encore saisie » —
 * que le stockage n'avait aucune raison de porter. C'est `ponctuelsLocaux` :
 * une liste d'identifiants, vivante le temps de l'edition, jamais enregistree.
 */

/** Le jour de la semaine d'une date « AAAA-MM-JJ », convention JS (dim = 0). */
export function weekdayDepuisDate(valeur) {
  if (typeof valeur !== 'string' || !valeur.trim()) return null;
  // Midi local : aucun decalage de fuseau ne peut faire basculer le jour.
  const d = new Date(valeur.trim().slice(0, 10) + 'T12:00:00');
  if (isNaN(d.getTime())) return null;
  // `new Date('2026-13-45T12:00:00')` est deja NaN, mais une date valide au
  // format tolere par le moteur (« 2026-8-9 ») ne doit pas passer pour autant :
  // on exige la forme stricte que l'input natif produit.
  if (!/^\d{4}-\d{2}-\d{2}$/.test(valeur.trim().slice(0, 10))) return null;
  return d.getDay();
}

/** Ce bloc est-il une date unique ? La base decide, l'ecran peut anticiper. */
export function estPonctuel(course, ponctuelsLocaux) {
  const c = course || {};
  if (typeof c.date === 'string' && c.date.trim()) return true;
  const locaux = Array.isArray(ponctuelsLocaux) ? ponctuelsLocaux : [];
  return locaux.indexOf(c.id) !== -1;
}

/**
 * Retour en hebdomadaire : la date est EFFACEE et le jour retenu est celui de
 * cette date. Le coach retrouve le creneau qu'il avait choisi au lieu d'un
 * dimanche par defaut — c'est le piege V255b, on ne le rejoue pas.
 */
export function basculerHebdo(course) {
  const c = course || {};
  const derive = weekdayDepuisDate(c.date);
  return {
    ...c,
    date: '',
    weekday: derive != null
      ? derive
      : (Number.isInteger(c.weekday) ? c.weekday : 0),
  };
}

/**
 * Le couple `(date, weekday)` tel qu'il part au serveur. Chaine VIDE et jamais
 * `null` : `PUT /courses` filtre les valeurs `None`, un `null` serait ignore et
 * une date ne pourrait alors PLUS JAMAIS etre effacee.
 *
 * `weekday` reste coherent avec `date` : le backend n'aiguille que sur `date`,
 * mais toute vue qui ne lit que `weekday` afficherait sinon un jour faux.
 */
export function payloadDateWeekday(course) {
  const c = course || {};
  const brute = typeof c.date === 'string' ? c.date.trim() : '';
  const derive = weekdayDepuisDate(brute);
  return {
    date: derive != null ? brute : '',
    weekday: derive != null
      ? derive
      : (Number.isInteger(c.weekday) ? c.weekday : parseInt(c.weekday, 10) || 0),
  };
}

/**
 * Les blocs annonces « date unique » dont la date manque encore.
 *
 * ON NE DEVINE PAS UNE DATE A LA PLACE DU COACH. Les enregistrer en l'etat les
 * reconvertirait en hebdomadaires en silence — exactement le genre de surprise
 * que ce lot corrige. On les signale, le coach tranche.
 */
export function ponctuelsSansDate(courses, ponctuelsLocaux) {
  const locaux = Array.isArray(ponctuelsLocaux) ? ponctuelsLocaux : [];
  return (courses || [])
    .filter((c) => locaux.indexOf((c || {}).id) !== -1
      && !(typeof (c || {}).date === 'string' && c.date.trim()))
    .map((c) => c.id);
}

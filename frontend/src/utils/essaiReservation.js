/**
 * essaiReservation.js — ESSAI-7 : du code obtenu a la seance reservee.
 *
 * POURQUOI CE FICHIER EXISTE. Jusqu'ici, la fin du tunnel d'essai etait un
 * cul-de-sac : `POST /checkout/free` reussissait, un bandeau disait « consultez
 * votre e-mail », et la personne restait sur la vitrine. Le seul chemin vers la
 * reservation passait par un e-mail — donc par une boite de reception, un
 * dossier « promotions », un delai. La mesure du 25/08/2026 l'a montre : le
 * code etait accorde, la seance ne l'etait pas.
 *
 * Ce module ne contient QUE des decisions pures — aucune requete, aucun DOM,
 * aucun stockage. C'est ce qui les rend verifiables une par une dans
 * `__tests__/essaiReservation.test.js`, sans navigateur ni base.
 *
 * DEUX INVARIANTS, et ils ne sont pas cosmetiques :
 *
 *   1. LE CODE VIENT DU SERVEUR, TOUJOURS. Le frontend ne reconstruit jamais un
 *      code AFR-, ne le relit pas depuis le localStorage, ne le devine pas
 *      depuis l'e-mail saisi. Sans octroi prouve par la reponse HTTP, il n'y a
 *      pas de cible : un refus anti-2e-essai ne doit RIEN ouvrir.
 *
 *   2. L'ETAT DE L'ESSAI RESTE CELUI DU SERVEUR. `t2_etat_essai` le derive au
 *      chargement de l'espace ; on ne le recalcule pas, on l'AVANCE d'un cran
 *      quand une reservation vient d'etre confirmee par le serveur dans la
 *      meme page. On ne fait jamais reculer un etat, et on n'en invente pas.
 */

/**
 * La forme EXACTE des codes produits par `_process_successful_payment` :
 * `AFR-` puis six caracteres pris dans A-Z et 0-9.
 *
 * Filtrer sur ce motif n'est pas de la coquetterie : la valeur atterrit dans
 * `window.location`. Un code non conforme ne doit pas pouvoir emmener ailleurs
 * que dans `/espace/`, ni produire un 404 apres un essai reellement accorde.
 */
export const MOTIF_CODE_AFR = /^AFR-[A-Z0-9]{6}$/;

/**
 * Le temps laisse a la confirmation d'etre lue avant que la page ne change.
 *
 * Ce n'est PAS une etape : personne n'a de bouton a cliquer, la suite arrive
 * toute seule. Assez long pour que « Ton cours d'essai est active ! » soit lu,
 * assez court pour qu'on ne croie pas le parcours fini. La destination repete
 * le message, donc rien n'est perdu si le regard etait ailleurs.
 */
export const DELAI_REDIRECTION_ESSAI_MS = 1400;

/**
 * Ou envoyer la personne apres `POST /checkout/free`.
 *
 * @param {object} reponse la reponse HTTP du serveur, telle quelle
 * @returns {string|null} `/espace/AFR-XXXXXX`, ou `null` s'il n'y a pas
 *          d'octroi prouve — auquel cas l'appelant ne redirige PAS.
 */
export function cibleRedirectionEssai(reponse) {
  if (!reponse || reponse.success !== true) return null;

  const brut = reponse.access_code;
  if (typeof brut !== 'string') return null;

  const code = brut.trim().toUpperCase();
  if (!MOTIF_CODE_AFR.test(code)) return null;

  return `/espace/${code}`;
}

/**
 * L'etat d'essai que l'espace participant doit MONTRER.
 *
 * `t2_etat_essai` repond au chargement ; une reservation faite dans la foulee
 * n'y figure pas encore. Sans ce rattrapage, l'ecran continuerait a reclamer
 * « choisis ta seance » a quelqu'un qui vient d'en choisir une — et il faudrait
 * recharger la page pour le voir changer.
 *
 * @param {object|null} trial le bloc `trial` renvoye par le serveur
 * @param {number} nbReservationsAVenir reservations futures connues de l'ecran
 * @returns {'available'|'booked'|'done'|null} `null` pour un forfait payant :
 *          son affichage ne change pas d'un pixel.
 */
export function etatEssaiAffiche(trial, nbReservationsAVenir) {
  if (!trial || trial.is_trial !== true) return null;

  // Une presence VALIDEE est definitive : elle ne redevient jamais « a
  // reserver », meme si une autre seance figure a l'agenda.
  if (trial.state === 'done') return 'done';
  if (trial.state === 'booked') return 'booked';

  const nb = Number(nbReservationsAVenir);
  return Number.isFinite(nb) && nb > 0 ? 'booked' : 'available';
}

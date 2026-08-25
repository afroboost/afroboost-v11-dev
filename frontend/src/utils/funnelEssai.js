/**
 * funnelEssai.js — ETAPE 1 : MESURER le parcours d'essai, sans le changer.
 *
 * POURQUOI CE FICHIER EXISTE. Avant lui, le depot ne contenait qu'UN SEUL
 * `posthog.capture` : le clic sur le CTA du Hero. Entre ce clic et la creation
 * du code AFR-, aucun evenement n'etait emis — ni l'ouverture du formulaire, ni
 * sa soumission, ni l'octroi. La baseline du 25/08/2026 a du etre reconstituee
 * a posteriori depuis MongoDB, et quatre des etapes demandees se sont revelees
 * STRUCTURELLEMENT non mesurables. Ce module ferme ce trou, et rien d'autre :
 * il ne modifie aucun parcours, aucun checkout, aucune regle metier.
 *
 * LES TROIS INVARIANTS, tous couverts par `__tests__/funnelEssai.test.js` :
 *
 *   1. UNE PANNE DE MESURE N'INTERROMPT JAMAIS UNE RESERVATION. Tout passe par
 *      un `try` unique et une valeur de retour ; rien ne remonte a l'appelant.
 *      PostHog est regulierement bloque par une extension : c'est le cas
 *      NORMAL, pas l'exception.
 *
 *   2. AUCUNE DONNEE PERSONNELLE NE PART. Les proprietes sont filtrees ici, au
 *      point de sortie, et pas au point d'appel — un appelant ajoute plus tard
 *      serait sinon la fuite. Voir `MOTIF_PERSONNEL`.
 *
 *   3. LA VARIANTE D'ENTREE SURVIT A LA REDIRECTION DU TUNNEL. Le tunnel Chat
 *      s'acheve en redirigeant vers `?offre=...&reserver=1` : le parametre
 *      `link` DISPARAIT de l'URL. Sans memoire, 100 % des parcours Chat
 *      seraient comptes « direct » et la comparaison Hero vs Chat serait
 *      exactement inversee. Voir `funnelVariante`.
 *
 * CE FICHIER NE FAIT PAS D'IDENTIFICATION. `posthog.identify()` et
 * `posthog.reset()` restent le monopole de `analyticsIdentity.js` (C9-B) :
 * chacun de ces appels peut declencher une fusion d'identite irreversible.
 */

/**
 * Les cinq etapes du funnel d'essai, et elles seules.
 *
 * La liste est FERMEE volontairement : un nom mal orthographie ne serait jamais
 * retrouve dans PostHog et trouerait la baseline en silence. Mieux vaut ne rien
 * envoyer et le voir en test que compter faux pendant sept jours.
 */
export const EVENEMENTS_FUNNEL = [
  'trial_cta_click',    // clic sur un CTA d'entree dans l'essai
  'trial_form_open',    // le formulaire de reservation s'ouvre reellement
  'trial_form_submit',  // la soumission a passe TOUTES les validations
  'trial_granted',      // POST /checkout/free reussi : le code existe
  // ESSAI-7 — LE PAS QUI MANQUAIT, et le seul qui compte vraiment.
  // `trial_granted` dit qu'un code existe ; il ne dit RIEN sur la venue au
  // cours. Entre les deux, la personne devait retrouver un e-mail, l'ouvrir,
  // cliquer, choisir une date. C'est la que le parcours se perdait, et
  // personne ne pouvait le voir. `session_booked` ne part qu'APRES la
  // confirmation du serveur : ni au clic, ni a l'ouverture du formulaire.
  'session_booked'
];

/** Cle de memorisation de la variante, pour la duree de l'onglet. */
export const CLE_VARIANTE = 'af_funnel_variante';

/**
 * Toute propriete dont le NOM evoque une personne est retiree.
 *
 * On filtre sur le nom plutot que sur une liste blanche : une liste blanche
 * oubliee un jour laisserait passer la fuite, alors qu'un motif trop large ne
 * coute qu'une propriete de mesure en moins. En cas de doute, on perd la
 * mesure, jamais la confidentialite.
 */
const MOTIF_PERSONNEL = /mail|name|nom|prenom|phone|tel|whatsapp|code|adresse|address|birth|naissance/i;

function nettoyer(proprietes) {
  const propres = {};
  const src = proprietes || {};
  Object.keys(src).forEach((cle) => {
    if (!MOTIF_PERSONNEL.test(cle)) propres[cle] = src[cle];
  });
  return propres;
}

/**
 * Emet un evenement du funnel. Renvoie TOUJOURS une chaine decrivant la
 * decision prise — c'est ce qui rend chaque refus testable — et ne leve jamais.
 *
 * @param {string} nom          l'un des `EVENEMENTS_FUNNEL`
 * @param {object} [proprietes] proprietes non personnelles (filtrees ici)
 * @param {object} [options]    options PostHog, ex. `{transport:'sendBeacon'}`
 *                              — indispensable quand le clic navigue dans la
 *                              foulee, sinon la requete est annulee.
 * @returns {'envoye'|'evenement-inconnu'|'posthog-indisponible'|'erreur'}
 */
export function funnelTracer(nom, proprietes, options) {
  try {
    if (EVENEMENTS_FUNNEL.indexOf(nom) === -1) return 'evenement-inconnu';

    const ph = window.posthog;
    if (!ph || typeof ph.capture !== 'function') return 'posthog-indisponible';

    // Deux arguments quand il n'y a pas d'options : c'est la forme employee
    // partout ailleurs, et un troisieme argument `undefined` n'est pas neutre
    // pour toutes les versions du SDK.
    if (options) ph.capture(nom, nettoyer(proprietes), options);
    else ph.capture(nom, nettoyer(proprietes));

    return 'envoye';
  } catch (e) {
    // Adblock, quota, SDK a moitie charge : la mesure est perdue, le parcours
    // continue. C'est l'invariant n°1.
    return 'erreur';
  }
}

/**
 * D'ou vient la personne, pour la duree de l'onglet.
 *
 *   'chat'      — entree par un lien de tunnel (`?link=`)
 *   'direct'    — entree sur une offre precise (`?offre=`)
 *   'organique' — ni l'un ni l'autre
 *   'inconnu'   — stockage inaccessible (navigation privee stricte)
 *
 * LA PREMIERE variante non organique gagne et est figee. C'est tout l'interet :
 * le tunnel Chat se termine par une redirection vers `?offre=...`, qui ferait
 * autrement basculer le parcours en « direct » juste avant la conversion.
 *
 * Une visite organique ne fige RIEN : la vraie entree, si elle survient plus
 * tard dans le meme onglet, reste mesurable.
 */
export function funnelVariante() {
  try {
    const memo = window.sessionStorage.getItem(CLE_VARIANTE);
    if (memo) return memo;

    const params = new URLSearchParams(window.location.search);
    let variante = 'organique';
    if (params.get('link')) variante = 'chat';
    else if (params.get('offre')) variante = 'direct';

    if (variante !== 'organique') window.sessionStorage.setItem(CLE_VARIANTE, variante);
    return variante;
  } catch (e) {
    return 'inconnu';
  }
}

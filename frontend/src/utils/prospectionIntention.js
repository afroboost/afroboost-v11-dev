/**
 * DEEPLINK PROSPECTION — L'INTENTION EST CAPTURÉE AVANT QUE REACT NE RENDE.
 * =========================================================================
 *
 * LE DÉFAUT QUE CE MODULE SUPPRIME. `coachMode` est initialisé de façon
 * SYNCHRONE depuis `localStorage` (App.js, `useState(() => …)`) : quand le
 * coach est déjà connecté — le cas normal quand il touche une notification —
 * `CoachDashboard` est monté DÈS LE PREMIER RENDU. Or React exécute les effets
 * des enfants AVANT ceux des parents. L'effet de montage du dashboard lisait
 * donc l'intention avant que l'effet d'App.js ne l'ait posée : il trouvait
 * `null`, repartait, et l'identifiant restait en `sessionStorage` sans que
 * personne ne le consomme jamais. Mesuré en production le 06/09 :
 * `afroboost_prospection_inbound` encore intact après le chargement, et la
 * conversation fermée.
 *
 * POURQUOI UN MODULE ET PAS UN EFFET DE PLUS. Un effet, où qu'on le place,
 * reste soumis à l'ordre de montage — on déplacerait la course sans la fermer.
 * L'import d'un module, lui, s'exécute au chargement du bundle : AVANT le
 * premier rendu, donc avant tout effet, sans exception possible. La capture
 * cesse d'être une étape du cycle de vie pour devenir un fait déjà acquis
 * quand React démarre.
 *
 * UNE SEULE SOURCE. Ce fichier est le SEUL à écrire et à effacer la clé.
 * App.js et CoachDashboard passent par lui et ne touchent jamais
 * `sessionStorage` directement : deux composants qui liraient et effaceraient
 * la même clé sans se coordonner, c'est précisément ce qui a produit le défaut.
 *
 * TROIS RÉPONSES, PAS DEUX. `lire()` rend :
 *   `null`  — aucune demande de prospection : le dashboard ne bascule pas ;
 *   `''`    — demande SANS cible (`?prospection=1` seul) : on ouvre l'onglet,
 *             on n'ouvre aucune conversation ;
 *   `'<id>'`— demande AVEC cible : on ouvre l'onglet ET la conversation.
 * C'est la sémantique que le dashboard appliquait déjà ; elle est conservée
 * mot pour mot, seul le moment de la capture change.
 *
 * ON NE STOCKE QUE L'IDENTIFIANT. Ni le nom de l'organisation, ni l'adresse,
 * ni le contenu du message : le strict nécessaire pour rouvrir la bonne
 * conversation. Et dans `sessionStorage`, jamais `localStorage` : l'intention
 * vaut pour CET onglet et cette venue — elle ne doit pas ressurgir demain.
 */

export const CLE = 'afroboost_prospection_inbound';

/* Un identifiant de message, borné. Une valeur absurde ne doit ni remplir le
   stockage ni voyager plus loin : elle sera simplement introuvable côté écran,
   qui sait déjà le dire sans rien casser. */
function nettoyer(valeur) {
  return String(valeur || '').trim().slice(0, 64);
}

/**
 * Extrait la cible d'une chaîne de requête. FONCTION PURE : elle n'écrit rien,
 * ce qui permet de la prouver seule, sans stockage ni navigateur.
 * Rend `null` quand il n'y a aucune demande de prospection.
 */
export function cibleDeRecherche(recherche) {
  let params;
  try {
    params = new URLSearchParams(String(recherche || '').replace(/^\?/, ''));
  } catch (e) {
    return null;
  }
  if (params.get('prospection') !== '1') return null;
  return nettoyer(params.get('inbound'));
}

/* L'ANNONCE, pour le cas où l'application est DÉJÀ ouverte.
   Quand le Service Worker remonte un `NOTIFICATION_CLICK`, la page ne se
   recharge pas : le dashboard est monté depuis longtemps et son effet de
   montage ne se rejouera jamais. Poser l'intention dans le stockage ne
   suffirait donc pas — personne n'irait la relire. Le module l'annonce, et
   c'est encore lui la source unique : un seul endroit écrit, un seul endroit
   prévient. */
export const EVENEMENT = 'afroboost:prospection-intention';

/** Écrit l'intention, puis l'annonce. Le mode privé peut refuser : on ne casse rien. */
export function poser(cible) {
  const valeur = nettoyer(cible);
  let ecrit = false;
  try {
    window.sessionStorage.setItem(CLE, valeur);
    ecrit = true;
  } catch (e) { /* navigation privée : l'annonce part quand même */ }
  try {
    window.dispatchEvent(new CustomEvent(EVENEMENT, { detail: valeur }));
  } catch (e) { /* environnement sans CustomEvent : le stockage a suffi */ }
  return ecrit;
}

/** Lit SANS effacer. Lire n'est pas consommer — c'est tout l'objet du correctif. */
export function lire() {
  try {
    return window.sessionStorage.getItem(CLE);
  } catch (e) {
    return null;
  }
}

/**
 * Efface. À n'appeler QUE sur un état terminal : la conversation a été ouverte,
 * ou elle est introuvable pour de bon. Effacer plus tôt — au montage, comme
 * avant — revient à jeter l'intention pendant que les conversations chargent
 * encore, c'est-à-dire à ne jamais l'honorer.
 */
export function consommer() {
  try {
    window.sessionStorage.removeItem(CLE);
    return true;
  } catch (e) {
    return false;
  }
}

/**
 * LA CAPTURE, exécutée à l'import — donc avant le premier rendu.
 * Nettoie aussi l'URL : un rafraîchissement ne doit pas rejouer l'intention,
 * et l'identifiant n'a rien à faire dans la barre d'adresse.
 * Rend ce qui a été capturé (`null` si rien), ce qui la rend testable.
 */
export function capturer() {
  if (typeof window === 'undefined' || !window.location) return null;
  const cible = cibleDeRecherche(window.location.search);
  if (cible === null) return null;
  poser(cible);
  try {
    window.history.replaceState({}, '', window.location.pathname + window.location.hash);
  } catch (e) { /* silencieux : l'intention est posée, c'est ce qui compte */ }
  return cible;
}

/* L'appel qui ferme la course. Il a lieu au chargement du module, donc avant
   que le moindre composant ne soit monté. */
export const CAPTURE_AU_CHARGEMENT = capturer();

export default {
  CLE, cibleDeRecherche, poser, lire, consommer, capturer,
};

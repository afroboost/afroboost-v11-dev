/**
 * P0-SOCLE — L'ÉTAT D'AUTHENTIFICATION, DÉCIDÉ EN UN SEUL ENDROIT.
 * =================================================================
 *
 * POURQUOI CE FICHIER EXISTE
 * --------------------------
 * Jusqu'ici, chaque écran reconstruisait sa propre idée de « suis-je connecté ? » :
 * l'un regardait `afroboost_coach_user`, l'autre la longueur de `afroboost_jwt`,
 * un troisième `afroboost_admin_persist`. Aucun ne savait distinguer « la session
 * est morte » de « cette ressource m'est refusée ». D'où le symptôme historique :
 * l'interface coach s'affichait, complète, pendant que le serveur refusait chaque
 * appel — sans qu'un seul écran sache le dire.
 *
 * Ce module est désormais la SEULE source de vérité sur quatre états :
 *
 *   EN_COURS  une connexion est en vol — on ne sait pas encore, on attend.
 *   VALIDE    un jeton signé, non expiré, est en poche.
 *   EXPIREE   l'interface se croit connectée mais aucune preuve signée
 *             exploitable n'existe (jeton périmé, ou jeton effacé alors que
 *             `afroboost_coach_mode` est resté — la « session zombie »).
 *   ANONYME   personne n'est connecté, et c'est normal (visiteur).
 *
 * CE QUE CE MODULE NE FAIT PAS
 * ----------------------------
 * Il ne contourne AUCUNE garde serveur, ne transforme aucun 403 en succès, et
 * n'accorde aucun droit. Seul le serveur juge. Ici on décide uniquement s'il
 * vaut la peine d'ENVOYER une requête dont on sait déjà qu'elle sera refusée,
 * et comment QUALIFIER un refus quand il arrive.
 *
 * Il n'invente pas non plus de nouveau système d'authentification : le jeton
 * reste émis par `/auth/login` seul, et lu par l'intercepteur axios d'App.js.
 */

import { jetonExpire } from './jwt';

export const AUTH = {
  EN_COURS: 'en_cours',
  VALIDE: 'valide',
  EXPIREE: 'expiree',
  ANONYME: 'anonyme',
};

/** Événement diffusé sur `window` à chaque changement d'état d'authentification. */
export const EVENEMENT_AUTH = 'afroboost:auth';

const CLE_JETON = 'afroboost_jwt';
const CLE_UTILISATEUR = 'afroboost_coach_user';
const CLE_MODE = 'afroboost_coach_mode';

/**
 * ROUTES À SIGNATURE OBLIGATOIRE.
 *
 * Cette liste n'est pas une supposition : chaque entrée a été vérifiée par un
 * appel RÉEL à la production le 18 août 2026 — `403` avec `X-User-Email` seul,
 * donc un jeton signé est indispensable. Côté serveur elles passent toutes par
 * `_v309_require_coach_or_admin` / `_v311_coach_email_from_jwt` / `coach_jwt_email`,
 * qui ignorent délibérément `X-User-Email`.
 *
 * ⚠️ RÈGLE V310c — NE JAMAIS DURCIR SANS PROUVER QUE LE CHEMIN LÉGITIME MARCHE.
 * N'ajouter une route ICI qu'après avoir mesuré `403` sans jeton ET `200` avec.
 * Sont VOLONTAIREMENT ABSENTES, bien qu'elles renvoient parfois 403 :
 *   - `/reservations`   : accepte le repli `X-User-Email` (mesuré 200). La bloquer
 *                         priverait de leurs réservations les sessions sans jeton.
 *   - `/chat/sessions`  : sa garde `_v319_coach_identity` dépend de l'interrupteur
 *                         serveur `REQUIRE_COACH_JWT`, qui peut être basculé sans
 *                         redéploiement. Un portillon figé côté navigateur
 *                         désobéirait à l'interrupteur.
 * Ces deux-là partent normalement ; leur éventuel refus est simplement qualifié.
 */
const ROUTES_SIGNATURE_REQUISE = [
  '/users',
  '/discount-codes',
  '/contacts/all',
  '/dashboard/all-transactions',
  '/credit-transactions',
  '/trash',
  '/coach/notifications',
  '/notifications/unread',
  '/chat/groups',
];

/** Nombre de connexions actuellement en vol (`/auth/login` en cours). */
let connexionsEnVol = 0;

function lire(cle) {
  try {
    return localStorage.getItem(cle);
  } catch (e) {
    return null;
  }
}

function diffuser(raison) {
  try {
    window.dispatchEvent(
      new CustomEvent(EVENEMENT_AUTH, { detail: { etat: etatAuth(), raison: raison || '' } })
    );
  } catch (e) {
    /* environnement sans window (tests unitaires purs) */
  }
}

/**
 * À appeler juste avant un `POST /auth/login`, et dans son `finally`.
 * Pendant ce laps de temps l'état vaut EN_COURS : les écrans attendent au lieu
 * de lancer des requêtes protégées qui partiraient sans jeton.
 */
export function debutConnexion() {
  connexionsEnVol += 1;
  diffuser('connexion');
}

export function finConnexion() {
  connexionsEnVol = Math.max(0, connexionsEnVol - 1);
  diffuser('connexion');
}

/** Remet le compteur à zéro — réservé aux tests. */
export function _reinitialiserConnexions() {
  connexionsEnVol = 0;
}

/** L'état d'authentification, lu à la demande (jamais mis en cache). */
export function etatAuth() {
  if (connexionsEnVol > 0) return AUTH.EN_COURS;

  const jeton = lire(CLE_JETON);
  if (jeton && String(jeton).length > 10) {
    return jetonExpire(jeton) ? AUTH.EXPIREE : AUTH.VALIDE;
  }

  // Pas de jeton exploitable. L'interface se croit-elle connectée malgré tout ?
  // C'est la SESSION ZOMBIE : `afroboost_coach_mode` survit indéfiniment alors
  // que le jeton, lui, expire en 7 jours et n'est jamais renouvelé. Historiquement
  // ce cas passait pour « connecté » et produisait des écrans à zéro, muets.
  if (lire(CLE_MODE) === 'true' || lire(CLE_UTILISATEUR)) return AUTH.EXPIREE;

  return AUTH.ANONYME;
}

/** Un jeton signé et non expiré est-il disponible ? */
export function authValide() {
  return etatAuth() === AUTH.VALIDE;
}

/**
 * Cette URL pointe-t-elle vers une route dont le serveur exige la signature ?
 * Tolère les URL absolues, le préfixe `/api`, et la chaîne de requête.
 */
export function signatureRequise(url) {
  if (!url) return false;
  const chemin = String(url)
    .split('?')[0]
    .replace(/^https?:\/\/[^/]+/i, '')
    .replace(/^\/api(?=\/)/, '');
  return ROUTES_SIGNATURE_REQUISE.some(
    (route) => chemin === route || chemin.indexOf(route + '/') === 0
  );
}

/**
 * QUALIFIER UN ÉCHEC — le cœur de la distinction demandée.
 *
 *   'session'     la PREUVE GLOBALE est en cause -> l'état de session doit changer.
 *   'droit'       la preuve est bonne, mais cette ressource-là est refusée
 *                 -> dégradation partielle, la session reste valable.
 *   'reseau'      aucune réponse (coupure, conteneur absent, mobile perdu).
 *   'serveur'     5xx.
 *   'introuvable' 404.
 *
 * La règle qui sépare 'session' de 'droit' : un 403 alors qu'AUCUNE preuve signée
 * n'est en poche ne peut pas être un problème de droit — c'est la session. Un 403
 * avec un jeton valide, en revanche, est un vrai refus sur cette ressource.
 */
export function classerEchec(err) {
  if (!err) return 'aucune';
  // Motif impose par l'appelant : sert aux reponses HTTP 200 dont le CORPS dit
  // l'echec (`{ success: false }`). Sans cela, une telle reponse passait pour un
  // succes vide — un « zero menteur » de plus, invisible cote reseau.
  if (err.motifAfroboost) return err.motifAfroboost;
  const reponse = err.response;
  if (!reponse) return 'reseau';

  const statut = reponse.status;
  if (statut === 401) return 'session';
  if (statut === 403) return authValide() ? 'droit' : 'session';
  if (statut === 404) return 'introuvable';
  if (statut >= 500) return 'serveur';
  return 'serveur';
}

/**
 * SORTIE PROPRE DE L'ÉTAT AUTHENTIFIÉ.
 *
 * Purge les TROIS clés d'un bloc. C'est le correctif du cycle auto-entretenu
 * hérité de V345 : l'intercepteur effaçait `afroboost_jwt` en laissant
 * `afroboost_coach_user`, de sorte qu'au rechargement suivant l'interface se
 * croyait toujours connectée, lançait ses requêtes, récoltait des 403 — et,
 * n'ayant plus de jeton à inspecter, ne disait plus rien du tout.
 *
 * Ne recharge PAS la page : la récupération appartient à l'application.
 */
export function terminerSession(raison) {
  try {
    localStorage.removeItem(CLE_JETON);
    localStorage.removeItem(CLE_UTILISATEUR);
    localStorage.removeItem(CLE_MODE);
  } catch (e) {
    /* stockage indisponible — l'événement part quand même */
  }
  diffuser(raison || 'expiree');
}

/**
 * Fabrique un echec QUALIFIE pour une reponse HTTP 200 dont le corps signale
 * pourtant un probleme. A utiliser dans un `appel` de `useChargement` : le
 * serveur a repondu, mais il n'a pas livre la donnee demandee.
 */
export function echecDeReponse(message, motif) {
  const err = new Error(message || 'Reponse invalide');
  err.motifAfroboost = motif || 'serveur';
  return err;
}

/** S'abonner aux changements d'état. Renvoie la fonction de désabonnement. */
export function abonnerAuth(rappel) {
  const gestionnaire = (evenement) => {
    const detail = (evenement && evenement.detail) || {};
    rappel({ etat: detail.etat || etatAuth(), raison: detail.raison || '' });
  };
  try {
    window.addEventListener(EVENEMENT_AUTH, gestionnaire);
  } catch (e) {
    return () => {};
  }
  return () => {
    try {
      window.removeEventListener(EVENEMENT_AUTH, gestionnaire);
    } catch (e) {
      /* rien */
    }
  };
}

/** Signale qu'un jeton vient d'être posé (après `/auth/login`). */
export function signalerConnexionReussie() {
  diffuser('connecte');
}

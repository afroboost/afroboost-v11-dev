/**
 * chatPolling.js — CHAT-LOOP1 : le sondage du dashboard cesse de dependre du
 * NOMBRE de conversations.
 *
 * CE QUI N'ALLAIT PAS. `CoachDashboard.js` executait `checkNewMessages` toutes
 * les 5 secondes : une boucle `for` sur TOUTES les sessions en mode humain,
 * avec un `GET /api/chat/sessions/<id>/messages` par session. En base, 69
 * sessions ont `is_ai_active` faux ou absent (`!undefined` vaut vrai) — soit
 * jusqu'a 828 requetes par minute, sans aucune garde de visibilite : portable
 * ferme, la boucle continuait. Mesure Cloudflare du 29/08 : 126 660 requetes
 * en 24 h depuis une seule IP, 98,69 k requetes bloquees, 73 % du trafic du
 * site. La regle « Anti-aspiration API Afroboost » (20 requetes / 10 s / IP)
 * coupait alors aussi le formulaire partenaire, qui partageait son compteur.
 *
 * POURQUOI CE MODULE EXISTE. `CoachDashboard.js` fait 7 200 lignes et n'est
 * monte par aucun banc. Une regle enfouie dedans serait intestable — or c'est
 * precisement l'invariant qu'il faut pouvoir prouver : le nombre de requetes
 * d'un cycle ne doit plus varier avec le nombre de conversations.
 */

/** Cadences en place. Inchangees par ce lot : il retire des requetes, pas du temps. */
export const CL1_INTERVALLE_SESSIONS = 5000;
export const CL1_INTERVALLE_CONVERSATIONS = 8000;
export const CL1_INTERVALLE_NOTIFICATIONS = 10000;
export const CL1_INTERVALLE_GROUPE = 10000;

/**
 * Faut-il lancer un sondage periodique maintenant ?
 *
 * Meme regle que `ChatWidget.js:5100`, qui l'appliquait deja cote visiteur :
 * onglet cache ou reseau absent -> on ne tire pas. Le dashboard ne l'avait pas.
 *
 * @param {string} etatVisibilite `document.visibilityState`
 * @param {boolean} enLigne `navigator.onLine`
 */
export function cl1DoitSonder(etatVisibilite, enLigne) {
  try {
    if (enLigne === false) return false;
    return etatVisibilite === 'visible';
  } catch (e) {
    // Une garde de confort ne doit jamais empecher le chat de fonctionner.
    return true;
  }
}

/**
 * Nombre de `GET /chat/sessions/<id>/messages` emis par un cycle de sondage.
 *
 * C'EST L'INVARIANT DU LOT. Avant : une requete par session humaine. Apres :
 * une seule, celle de la conversation OUVERTE — et zero si aucune ne l'est.
 * Le resultat ne depend plus de `nbSessionsHumaines`, qui n'est la que pour
 * que le banc puisse le prouver sur toute la plage.
 *
 * @param {number} nbSessionsHumaines sessions en mode humain (ignore : c'est le point)
 * @param {boolean} sessionOuverte une conversation est-elle selectionnee ?
 */
export function cl1RequetesMessagesParCycle(nbSessionsHumaines, sessionOuverte) {
  return sessionOuverte ? 1 : 0;
}

/**
 * Volume horaire de requetes de messages, a cadence donnee.
 * Sert au banc a chiffrer la reduction sans lancer la moindre charge reelle.
 */
export function cl1RequetesParHeure(nbParCycle, intervalleMs) {
  if (!intervalleMs || intervalleMs <= 0) return 0;
  return nbParCycle * (3600000 / intervalleMs);
}

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

/* ═══════════════════════ CHAT-LOOP2 ═══════════════════════ */
/**
 * CHAT-LOOP2 — L'ANGLE MORT DE CHAT-LOOP1.
 *
 * La validation en production du 29/08 a montre que CHAT-LOOP1 avait garde
 * 3 des 8 `setInterval` de `CoachDashboard.js`. Le plus couteux des cinq
 * oublies, `v441ChargerNonLus`, tirait `GET /api/private/nonlus` toutes les
 * 5 secondes sur TOUS les onglets du dashboard, sans garde et sans recul sur
 * erreur — soit 17 280 requetes/24 h, en 403 dans une session sans jeton.
 *
 * POURQUOI LE BANC DE CHAT-LOOP1 NE L'A PAS VU : il verifiait que la CHAINE
 * `cl1DoitSonder(` etait PRESENTE dans le fichier, et qu'elle y etait au moins
 * 3 fois. Un fichier qui garde 3 pollers sur 8 passait donc au vert. Un test
 * de presence ne prouve jamais une couverture.
 *
 * Ce que ce module ajoute : de quoi ENUMERER les sites d'appel et exiger que
 * CHACUN soit garde — ou declare, avec sa raison, dans le registre ci-dessous.
 */

/**
 * Registre des sondages periodiques de `CoachDashboard.js`.
 *
 * `repriseImmediate` : faut-il rappeler la fonction au retour a l'ecran, en
 * plus de laisser l'intervalle repartir ? OUI seulement quand l'attente serait
 * visible (cadences de 30 s et 60 s). NON pour les cadences rapides (3 s, 5 s) :
 * le prochain tir arrive avant que l'oeil ne s'en apercoive, et un rappel de
 * plus ne serait qu'une rafale de rattrapage. Jamais un `setInterval` de plus.
 *
 * Toute entree `fondAutorise: false` DOIT porter la garde a son site d'appel.
 * Ajouter un `setInterval` sans l'inscrire ici fait echouer le banc : c'est
 * exactement le garde-fou qui manquait.
 */
export const CL2_POLLERS_DASHBOARD = [
  {
    cle: 'badge-session',
    repriseImmediate: true,
    fonction: 'SessionSecureBadge / check',
    endpoint: 'GET /auth/whoami',
    intervalleMs: 60000,
    reseau: true,
    fondAutorise: false,
    raison: "Indicateur visuel « Session securisee ». Personne ne le lit onglet cache.",
  },
  {
    cle: 'sante-scheduler',
    repriseImmediate: true,
    fonction: 'checkSchedulerHealth',
    endpoint: 'GET /scheduler/health',
    intervalleMs: 30000,
    reseau: true,
    fondAutorise: false,
    raison: "Affichage d'etat de l'onglet Campagnes. Aucun effet metier.",
  },
  {
    cle: 'declencheur-campagnes',
    repriseImmediate: true,
    fonction: 'triggerCheck',
    endpoint: 'GET /cron/check-campaigns puis GET /campaigns',
    intervalleMs: 60000,
    reseau: true,
    fondAutorise: false,
    raison:
      "Vestige de l'ere Vercel. DEUX preuves qu'il n'est plus indispensable : " +
      "(1) le serveur lance `_campaign_scheduler_loop()` au demarrage, qui envoie " +
      "les campagnes programmees toutes les 60 s ; (2) `/cron/check-campaigns` " +
      "repond 401 au frontend, le declencheur est donc deja inerte. Seul le " +
      "rafraichissement de la liste subsistait, et il n'a d'interet que visible.",
  },
  {
    cle: 'progression-envoi',
    repriseImmediate: false,
    fonction: 'pollSending',
    endpoint: 'GET /campaigns/<id>/status',
    intervalleMs: 3000,
    reseau: true,
    fondAutorise: false,
    raison:
      "Barre de progression d'un envoi en cours. Le statut est relu au retour a " +
      "l'ecran. NOTE : ce poller boucle sur les campagnes en statut `sending` — " +
      "meme motif que la boucle supprimee par CHAT-LOOP1, mais N vaut 0 ou 1 en " +
      "pratique. Hors perimetre de ce lot, consigne ici pour ne pas etre oublie.",
  },
  {
    cle: 'nonlus-whatsapp',
    repriseImmediate: false,
    fonction: 'v441ChargerNonLus',
    endpoint: 'GET /private/nonlus',
    intervalleMs: 5000,
    reseau: true,
    fondAutorise: false,
    raison:
      "Pastille des WhatsApp non lus (V441). C'EST LE POLLER DE CHAT-LOOP2 : " +
      "5 s sur tous les onglets, 17 280 requetes/24 h. Une pastille ne se lit pas " +
      "onglet cache ; elle est recalculee au retour a l'ecran.",
  },
];

/**
 * Enumere les sites d'appel `setInterval(...)` d'un source et dit, pour chacun,
 * s'il porte la garde de visibilite.
 *
 * On lit le SITE D'APPEL, pas la fonction appelee : `setInterval(f, 5000)` est
 * compte comme NON garde meme si `f` contient la garde. C'est voulu — la garde
 * doit rester visible la ou la cadence est posee, sinon la relecture d'un
 * `setInterval` ne permet plus de savoir s'il tire onglet cache.
 *
 * @param {string} source contenu du fichier
 * @returns {Array<{intervalleMs:number|null, garde:boolean, extrait:string}>}
 */
export function cl2AnalyserSetIntervals(source) {
  const sites = [];
  const motif = /setInterval\s*\(/g;
  let m;
  while ((m = motif.exec(source)) !== null) {
    let i = m.index + m[0].length;
    let profondeur = 1;
    while (i < source.length && profondeur > 0) {
      const c = source[i];
      if (c === '(') profondeur += 1;
      else if (c === ')') profondeur -= 1;
      i += 1;
    }
    const extrait = source.slice(m.index, i);
    const cadence = extrait.match(/,\s*(\d+)\s*\)\s*$/);
    sites.push({
      intervalleMs: cadence ? Number(cadence[1]) : null,
      garde: extrait.indexOf('cl1DoitSonder(') !== -1,
      extrait: extrait.replace(/\s+/g, ' ').slice(0, 110),
    });
  }
  return sites;
}

/** Requetes par jour d'un sondage a cadence donnee, dashboard ouvert en continu. */
export function cl2RequetesParJour(intervalleMs) {
  if (!intervalleMs || intervalleMs <= 0) return 0;
  return Math.round(86400000 / intervalleMs);
}

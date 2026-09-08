/**
 * F3 — ENTRER DANS SPORDATEUR SANS ATTENTE VISIBLE, EN RESTANT CONNECTÉ.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * LE PROBLÈME, ET POURQUOI UN 302 SERVEUR NE MARCHE PAS
 * ─────────────────────────────────────────────────────────────────────────
 * Le clic « Spordateur » faisait : POST /spordate/access → ATTENDRE le jeton →
 * naviguer. L'attente donnait l'impression d'une page Afroboost intermédiaire.
 *
 * Un handoff serveur pur (clic → GET → 302) est IMPOSSIBLE ici : Afroboost
 * authentifie par un JWT en localStorage, envoyé par l'intercepteur axios dans
 * un EN-TÊTE. Une navigation navigateur (GET) n'emporte pas cet en-tête — le
 * serveur ne saurait pas qui entre. On garde donc l'auto-login (le jeton reste
 * indispensable), mais on SUPPRIME L'ATTENTE en préparant le jeton AVANT le
 * clic : au survol ou au focus du lien, on le pré-obtient ; au clic, il est
 * déjà là et la navigation est immédiate.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * CE QU'ON NE CHANGE PAS
 * ─────────────────────────────────────────────────────────────────────────
 * L'auto-login est conservé. Le `href` reste vrai (clic milieu / nouvel onglet
 * marchent). Si le pré-chargement n'a pas eu lieu (clic sans survol, mobile),
 * on retombe sur le comportement d'avant : POST court puis navigation, avec un
 * filet pour toujours partir.
 */
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

// Le jeton d'accès a une durée de vie courte (15 min côté serveur). On ne
// garde le nôtre en cache que 5 min pour rester loin de l'expiration.
const FRAICHEUR_MS = 5 * 60 * 1000;

let _cache = null;      // { url, obtenuA }
let _enVol = null;      // promesse en cours, pour ne pas lancer deux POST

/** Le jeton en cache est-il encore assez frais pour naviguer sans risque ? */
function fraisEtValide() {
  return _cache && _cache.url && (Date.now() - _cache.obtenuA) < FRAICHEUR_MS;
}

/**
 * Pré-obtient (ou rafraîchit) le jeton de passage. Idempotent et silencieux :
 * appelé au survol/focus du lien, il ne dérange rien s'il échoue — le clic
 * retombera sur le chemin normal. Ne relance pas si un appel est déjà en vol
 * ou si le cache est encore frais.
 */
export function prechargerSpordate() {
  if (fraisEtValide() || _enVol) return _enVol || Promise.resolve();
  _enVol = axios.post(`${API}/spordate/access`, {}, { timeout: 2500 })
    .then((r) => {
      const url = (r && r.data && r.data.url) || '/rencontre';
      _cache = { url, obtenuA: Date.now() };
      return url;
    })
    .catch(() => { /* silencieux : le clic gérera */ })
    .finally(() => { _enVol = null; });
  return _enVol;
}

/**
 * Ajoute une destination interne (`?next=/profile`) à l'URL de passage, sans
 * l'écraser si un `t` y est déjà. `next` est validé côté Spordateur ; ici on se
 * contente d'un chemin interne commençant par `/`.
 */
function avecNext(url, next) {
  if (!next || next[0] !== '/') return url;
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}next=${encodeURIComponent(next)}`;
}

/**
 * ENTRER DANS SPORDATEUR. Navigation garantie, sans écran intermédiaire.
 *   - jeton frais en cache -> navigation IMMÉDIATE (le cas nominal après survol) ;
 *   - sinon -> on lance le POST et on navigue dès sa réponse, avec un filet
 *     qui part sur /rencontre si le réseau traîne.
 * `next` (optionnel) = page interne à ouvrir déjà connecté (ex. '/profile').
 */
export function entrerDansSpordate(next) {
  let parti = false;
  const aller = (url) => {
    if (parti) return;
    parti = true;
    window.location.href = avecNext(url || '/rencontre', next);
  };

  if (fraisEtValide()) {           // ← le cas qui supprime l'attente
    aller(_cache.url);
    return;
  }

  // Pas de jeton prêt : on part quoi qu'il arrive, au plus tard après le filet.
  const filet = setTimeout(() => aller('/rencontre'), 1500);
  (async () => {
    try {
      const r = await axios.post(`${API}/spordate/access`, {}, { timeout: 1500 });
      aller((r && r.data && r.data.url) || '/rencontre');
    } catch {
      aller('/rencontre');        // 403/503 = normal : Spordate propose son login
    } finally {
      clearTimeout(filet);
    }
  })();
}

/** Pour les tests : vider le cache entre deux scénarios. */
export function _resetHandoffPourTest() {
  _cache = null;
  _enVol = null;
}

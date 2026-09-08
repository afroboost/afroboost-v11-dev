/**
 * F3 FINAL — ENTRER DANS SPORDATEUR SANS AUCUNE ATTENTE, MOBILE COMPRIS.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * DEUX CHEMINS, PARCE QUE L'IDENTITÉ VIT À DEUX ENDROITS
 * ─────────────────────────────────────────────────────────────────────────
 * Afroboost porte l'identité de deux façons :
 *   - un ABONNÉ (public principal du lien) : jeton d'appareil / code, envoyé
 *     par l'intercepteur axios dans un EN-TÊTE. Une navigation navigateur (GET)
 *     n'emporte AUCUN en-tête -> le serveur ne saurait pas qui entre ;
 *   - un COACH connecté par mot de passe / Google : possède AUSSI le cookie
 *     httpOnly `coach_session_token`, que le navigateur emporte, lui.
 *
 * D'où deux mécanismes complémentaires :
 *   1. `GET /api/spordate/enter` : handoff SERVEUR pur (302) pour les porteurs
 *      du cookie. Clic -> le navigateur PART TOUT DE SUITE, le serveur signe et
 *      redirige. Zéro fetch client, zéro attente.
 *   2. Pour les abonnés (en-tête, pas de cookie) : on PRÉ-OBTIENT le jeton AU
 *      MONTAGE de l'écran (pas seulement au survol — le mobile n'a pas de
 *      survol). Au tap, le jeton est déjà là : navigation immédiate.
 *
 * Le tap n'attend JAMAIS un fetch : soit le jeton est déjà en cache (navigation
 * directe), soit on part sur la route serveur (navigation immédiate). L'ancien
 * « POST puis on attend la réponse pour naviguer » a disparu.
 *
 * On NE CHANGE PAS l'auto-login (le jeton reste indispensable côté Spordate) ni
 * le fait que le `href` demeure une URL réelle (clic milieu / nouvel onglet).
 */
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

// Le jeton d'accès vit 15 min côté serveur. On ne garde le nôtre que 5 min en
// cache pour rester loin de l'expiration.
const FRAICHEUR_MS = 5 * 60 * 1000;

let _cache = null;      // { url, obtenuA }
let _enVol = null;      // POST en cours, pour ne pas en lancer deux

function fraisEtValide() {
  return _cache && _cache.url && (Date.now() - _cache.obtenuA) < FRAICHEUR_MS;
}

/** Y a-t-il, côté navigateur, un indice qu'une identité Afroboost existe ? Sert
 * à ne PAS précharger (donc à ne pas provoquer un 403 inutile) pour un visiteur
 * anonyme, qui de toute façon n'obtiendrait aucun jeton. Le cookie coach, lui,
 * est httpOnly (illisible ici) : ces coachs passent par la route serveur. */
function aUneIdentiteAfroboost() {
  try {
    var cles = ['afroboost_jwt', 'afroboost_subscriber_token', 'afroboost_identity',
                'afroboost_admin_persist', 'afroboost_espace_token'];
    for (var i = 0; i < cles.length; i++) {
      if (localStorage.getItem(cles[i])) return true;
    }
  } catch (e) { /* localStorage indisponible : on tentera quand même */ return true; }
  return false;
}

/**
 * Pré-obtient (ou rafraîchit) le jeton de passage. Idempotent et silencieux :
 * appelé au montage de l'écran, au survol ou au focus, il ne dérange rien s'il
 * échoue. Ne relance pas si un appel est déjà en vol ou si le cache est frais.
 * Sans identité connue côté navigateur, on ne tente rien (pas de 403 anonyme).
 */
export function prechargerSpordate() {
  if (fraisEtValide() || _enVol) return _enVol || Promise.resolve();
  if (!aUneIdentiteAfroboost()) return Promise.resolve();
  _enVol = axios.post(`${API}/spordate/access`, {}, { timeout: 2500 })
    .then((r) => {
      const url = (r && r.data && r.data.url) || '/rencontre';
      _cache = { url, obtenuA: Date.now() };
      return url;
    })
    .catch(() => { /* silencieux : le tap gérera via la route serveur */ })
    .finally(() => { _enVol = null; });
  return _enVol;
}

/** Ajoute une destination interne (`?next=/profile`) sans écraser un `t` déjà là. */
function avecNext(url, next) {
  if (!next || next[0] !== '/') return url;
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}next=${encodeURIComponent(next)}`;
}

/** L'URL de la route serveur de handoff, avec la destination éventuelle. */
export function urlEntreeServeur(next) {
  const base = `${API}/spordate/enter`;
  return (next && next[0] === '/') ? `${base}?next=${encodeURIComponent(next)}` : base;
}

/**
 * ENTRER DANS SPORDATEUR. La navigation démarre IMMÉDIATEMENT, sans attendre
 * aucun fetch :
 *   - jeton frais en cache (cas nominal après préchargement au montage) ->
 *     navigation DIRECTE vers /rencontre?t=… ;
 *   - sinon -> navigation vers la route serveur `/api/spordate/enter`, qui
 *     signe et redirige (302) pour les sessions à cookie, ou renvoie proprement
 *     vers /rencontre sinon.
 * `next` (optionnel) = page interne à ouvrir déjà connecté (ex. '/profile').
 */
export function entrerDansSpordate(next) {
  if (fraisEtValide()) {
    window.location.href = avecNext(_cache.url, next);
    return;
  }
  // Aucun jeton prêt : on PART TOUT DE SUITE vers la route serveur. Pas de POST
  // bloquant, pas de setTimeout, pas d'écran d'attente.
  window.location.href = urlEntreeServeur(next);
}

/** Pour les tests : vider le cache entre deux scénarios. */
export function _resetHandoffPourTest() {
  _cache = null;
  _enVol = null;
}

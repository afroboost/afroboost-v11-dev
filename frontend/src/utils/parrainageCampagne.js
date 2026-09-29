/**
 * PAR-3 — ENTRÉE DE CAMPAGNE : le lien /duo/c/<token> partagé par un coach.
 *
 * Le serveur (POST /api/referral/campaign/{token}/entry) crée UNE invitation
 * racine pour ce visiteur et renvoie son `share_token` ; la page publique
 * /duo/<share_token> (InvitationDuo + WizardFilleul) fait tout le reste.
 *
 * RÈGLE « JAMAIS DE BOUCLE D'APPELS » : une entrée déjà connue sur cet appareil
 * (localStorage `afroboost_campagne_<tok>`) ne refait AUCUN appel ; un appel en
 * cours pour un même jeton est PARTAGÉ (jamais deux POST simultanés, même si le
 * composant est démonté puis remonté).
 *
 * AUCUNE DONNÉE PERSONNELLE : on ne stocke que {share_token, entry_key}.
 */
import axios from 'axios';
import { attributionEnregistrer, attributionActuelle } from './attribution';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
export const API_CAMPAGNE_ENTREE = `${BACKEND_URL}/api/referral/campaign`;

const JETON_OK = /^[A-Za-z0-9_-]{1,128}$/;
const CIBLE_OK = /^\/duo\/[A-Za-z0-9_-]+\/?$/;

/** Redirection injectable (les tests remplacent `remplacer`). */
export const navigation = {
  remplacer(url) { window.location.replace(url); },
};

export function cleCampagne(token) {
  return `afroboost_campagne_${token}`;
}

/** {share_token?, entry_key?} mémorisé pour cette campagne, sinon null. */
export function lireEntreeCampagne(token) {
  try {
    const brut = window.localStorage.getItem(cleCampagne(token));
    if (!brut) return null;
    const o = JSON.parse(brut);
    if (!o || typeof o !== 'object') return null;
    const res = {};
    if (typeof o.share_token === 'string' && JETON_OK.test(o.share_token)) res.share_token = o.share_token;
    if (typeof o.entry_key === 'string' && o.entry_key) res.entry_key = o.entry_key;
    return (res.share_token || res.entry_key) ? res : null;
  } catch (e) {
    return null;
  }
}

export function ecrireEntreeCampagne(token, entree) {
  try {
    window.localStorage.setItem(cleCampagne(token), JSON.stringify(entree));
  } catch (e) { /* mode privé : une nouvelle entrée sera demandée au retour */ }
}

/** La page de l'invitation. Une cible serveur hors /duo/<jeton> est ignorée. */
export function cibleInvitation(shareToken, target) {
  if (typeof target === 'string' && CIBLE_OK.test(target)) return target;
  return `/duo/${encodeURIComponent(shareToken)}`;
}

/** L'origine du visiteur (dont ?ref=), comme le reste du site. Jamais bloquant. */
function attributionPourEntree() {
  try {
    const a = attributionEnregistrer(window.location.search, document.referrer, window.location.pathname);
    if (a) return a;
  } catch (e) { /* le suivi ne bloque jamais le parcours */ }
  try { return attributionActuelle(); } catch (e) { return null; }
}

const enCours = {};

/** Tests uniquement : oublie les appels en cours (un appel suspendu d'un cas ne fuit pas dans le suivant). */
export function _resetEntreesPourTest() {
  Object.keys(enCours).forEach((k) => { delete enCours[k]; });
}

/**
 * UN POST d'entrée. Résout {share_token, entry_key, target} (déjà mémorisés),
 * rejette {status, raison, detail} (status 0 = réseau).
 */
export function entrerCampagne(token) {
  if (enCours[token]) return enCours[token];
  const connue = lireEntreeCampagne(token);
  const headers = {};
  if (connue && connue.entry_key) headers['X-Entry-Key'] = connue.entry_key;
  const corps = {};
  const attribution = attributionPourEntree();
  if (attribution) corps.attribution = attribution;
  const p = axios.post(`${API_CAMPAGNE_ENTREE}/${encodeURIComponent(token)}/entry`, corps, { timeout: 20000, headers })
    .then((r) => {
      const d = (r && r.data) || {};
      if (typeof d.share_token !== 'string' || !JETON_OK.test(d.share_token)) {
        const err = { status: 0, raison: '', detail: '' };
        throw err;
      }
      const entry = (typeof d.entry_key === 'string' && d.entry_key) ? d.entry_key : ((connue && connue.entry_key) || '');
      const entree = { share_token: d.share_token };
      if (entry) entree.entry_key = entry;
      ecrireEntreeCampagne(token, entree);
      return Object.assign({}, entree, { target: cibleInvitation(d.share_token, d.target) });
    }, (err) => {
      const rep = err && err.response;
      if (!rep) throw { status: 0, raison: '', detail: '' }; // eslint-disable-line no-throw-literal
      const h = rep.headers || {};
      throw { // eslint-disable-line no-throw-literal
        status: rep.status || 0,
        raison: h['x-refus-raison'] || h['X-Refus-Raison'] || '',
        detail: (rep.data && rep.data.detail) || '',
      };
    })
    .finally(() => { delete enCours[token]; });
  enCours[token] = p;
  return p;
}

/** Message clair, sans technique. `null` = erreur réseau (bouton Réessayer). */
export function messageEntreeCampagne(refus) {
  const s = refus && refus.status;
  if (s === 404) return "Cette invitation n'est plus disponible.";
  if (s === 410) return 'La séance de cette invitation est passée.';
  if (s === 409 && refus.raison === 'campagne_complete') return 'Cette invitation a atteint son nombre maximal de places.';
  if (s === 409) return "Cette invitation n'est plus disponible.";
  if (s === 429) return 'Trop de tentatives, réessaie dans un instant.';
  return null;
}

/**
 * V610m — CET APPAREIL participe-t-il déjà à l'événement de cette invitation ?
 *
 * Mémoire LOCALE seulement (jamais une donnée personnelle) :
 *   - après un paiement : l'identifiant de session Stripe (`cs_…`), RE-VÉRIFIÉ par le
 *     serveur (`/api/invitation/relais/session/<cs>` -> `place_confirmee`) avant
 *     d'afficher quoi que ce soit ;
 *   - après une place offerte (membre 8 mois) : le lien personnel rendu par le serveur.
 * Un autre appareil, ou une mémoire effacée : la page d'invitation normale.
 *
 * L'INTENTION « place offerte » : le membre touche « Réserve gratuitement » sur la page
 * de l'invitation -> l'offre visée est retenue (24 h) pour que son espace s'ouvre
 * DIRECTEMENT sur CET événement (même après le lien d'accès reçu par e-mail).
 */
const PREFIXE = 'af_evt_participe_';
const CLE_INTENTION = 'af_evt_vise';
const DUREE_INTENTION_MS = 24 * 3600 * 1000;
const RE_JETON = /^[A-Za-z0-9_-]{16,64}$/;
const RE_CS = /^cs_[A-Za-z0-9_]{6,200}$/;

function lire(cle) {
  try { return JSON.parse(window.localStorage.getItem(cle) || 'null'); } catch (e) { return null; }
}
function ecrire(cle, valeur) {
  try { window.localStorage.setItem(cle, JSON.stringify(valeur)); } catch (e) { /* stockage indisponible */ }
}

/** Mémorise la participation pour le jeton d'invitation ouvert (`{cs}` ou `{relais}`). */
export function memoriserParticipation(jeton, { cs, relais } = {}) {
  if (!RE_JETON.test(String(jeton || ''))) return;
  if (cs && RE_CS.test(String(cs))) { ecrire(PREFIXE + jeton, { cs: String(cs) }); return; }
  if (relais && RE_JETON.test(String(relais.jeton || '')) && /^https:\/\//.test(String(relais.share_url || ''))) {
    ecrire(PREFIXE + jeton, { relais: { jeton: String(relais.jeton), share_url: String(relais.share_url) } });
  }
}

/** `{cs}` | `{relais}` | null — jamais autre chose. */
export function lireParticipation(jeton) {
  if (!RE_JETON.test(String(jeton || ''))) return null;
  const o = lire(PREFIXE + jeton);
  if (!o || typeof o !== 'object') return null;
  if (RE_CS.test(String(o.cs || ''))) return { cs: String(o.cs) };
  const r = o.relais;
  if (r && RE_JETON.test(String(r.jeton || '')) && /^https:\/\//.test(String(r.share_url || ''))) {
    return { relais: { jeton: String(r.jeton), share_url: String(r.share_url) } };
  }
  return null;
}

/** Le membre veut SA place offerte pour cette offre (venu de l'invitation `jeton`). */
export function retenirIntentionMembre(offreId, jeton) {
  const o = String(offreId || '');
  if (!/^[A-Za-z0-9_-]{4,80}$/.test(o)) return;
  ecrire(CLE_INTENTION, { offre: o, jeton: RE_JETON.test(String(jeton || '')) ? String(jeton) : '', t: Date.now() });
}

/** `{offre, jeton}` encore valable (24 h), sinon null. */
export function lireIntentionMembre(maintenant = Date.now()) {
  const o = lire(CLE_INTENTION);
  if (!o || typeof o !== 'object' || !/^[A-Za-z0-9_-]{4,80}$/.test(String(o.offre || ''))) return null;
  if (!(Number(o.t) > 0) || maintenant - Number(o.t) > DUREE_INTENTION_MS) return null;
  return { offre: String(o.offre), jeton: RE_JETON.test(String(o.jeton || '')) ? String(o.jeton) : '' };
}

export function oublierIntentionMembre() {
  try { window.localStorage.removeItem(CLE_INTENTION); } catch (e) { /* ignore */ }
}

/** L'offre de l'événement depuis la page publique : réservation directe, sinon `/?offre=<id>`. */
export function offreDeLInvitation(d) {
  const x = d || {};
  if (x.reservation_directe && x.reservation_directe.offer_id) return String(x.reservation_directe.offer_id);
  const m = /[?&]offre=([A-Za-z0-9_-]{4,80})/.exec(String(x.target_url || x.cible || ''));
  return m ? m[1] : '';
}

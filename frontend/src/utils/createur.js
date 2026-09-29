/**
 * V559 — PROGRAMME CRÉATEUR : les appels réseau (un seul module pour l'espace
 * abonné, le dashboard coach et la console super-admin).
 *
 * IDENTITÉ : l'appelant fournit ses en-têtes (`enteteParrain()` pour l'espace
 * abonné ; rien pour un coach : l'intercepteur axios pose déjà son JWT). Le
 * serveur décide seul du rôle — jamais le navigateur.
 */
import axios from 'axios';

const BASE = `${process.env.REACT_APP_BACKEND_URL || ''}/api/createur`;
const DELAI = 15000;

const options = (entetes) => ({ timeout: DELAI, headers: (typeof entetes === 'function' ? entetes() : entetes) || {} });

export const lireCreateur = (entetes) => axios.get(`${BASE}/me`, options(entetes)).then((r) => (r && r.data) || null);
export const envoyerDemandeCreateur = (corps, entetes) => axios.post(`${BASE}/demande`, corps, options(entetes))
  .then((r) => (r && r.data) || null);
export const demanderRetrait = (entetes) => axios.post(`${BASE}/retrait`, {}, options(entetes))
  .then((r) => (r && r.data) || null);

// ── Super-admin (JWT posé par l'intercepteur) ─────────────────────────────────
export const adminLister = (quoi, statut) => axios.get(`${BASE}/admin/${quoi}`,
  { timeout: DELAI, params: statut ? { statut } : {} }).then((r) => (r && r.data) || {});
export const adminDecisionCreateur = (id, decision) => axios.post(
  `${BASE}/admin/createurs/${encodeURIComponent(id)}/decision`, { decision }, { timeout: DELAI }).then((r) => r.data);
export const adminCreerProgramme = (corps) => axios.post(`${BASE}/admin/programmes`, corps, { timeout: DELAI })
  .then((r) => r.data);
export const adminModifierProgramme = (id, corps) => axios.put(
  `${BASE}/admin/programmes/${encodeURIComponent(id)}`, corps, { timeout: DELAI }).then((r) => r.data);
export const adminAnnulerCommission = (id, motif) => axios.post(
  `${BASE}/admin/commissions/${encodeURIComponent(id)}/annuler`, { motif }, { timeout: DELAI }).then((r) => r.data);
export const adminDecisionRetrait = (id, decision) => axios.post(
  `${BASE}/admin/retraits/${encodeURIComponent(id)}/decision`, { decision }, { timeout: DELAI }).then((r) => r.data);

/** Le message FR d'une erreur axios (le `detail` du serveur s'il est lisible). */
export function messageErreurCreateur(err, repli) {
  const rep = (err && err.response) || {};
  const d = rep.data && rep.data.detail;
  if (typeof d === 'string' && d.trim()) return d;
  if (rep.status === 401 || rep.status === 403) return 'Reconnecte-toi à ton espace pour continuer.';
  if (rep.status === 429) return 'Trop de tentatives. Réessaie dans un instant.';
  return repli || 'Action impossible pour le moment. Réessaie dans un instant.';
}

/** « 15.00 CHF » */
export function chf(montant) {
  const n = Number(montant);
  return `${(Number.isFinite(n) ? n : 0).toFixed(2)} CHF`;
}

/** « 30 sept. 2026 » (heure suisse) ; '' si illisible. */
export function dateCourte(iso) {
  const d = new Date(String(iso || ''));
  if (Number.isNaN(d.getTime())) return '';
  try {
    return new Intl.DateTimeFormat('fr-CH', { timeZone: 'Europe/Zurich', day: 'numeric', month: 'short', year: 'numeric' }).format(d);
  } catch (e) { return ''; }
}

/** Libellé de la carte d'accès selon le statut (menu de l'espace abonné / coach). */
export function libelleAccesCreateur(statut) {
  return statut === 'approved' ? 'Dashboard Créateur' : 'Devenir créateur Afroboost';
}

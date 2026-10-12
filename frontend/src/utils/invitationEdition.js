/**
 * V610e — L'ÉDITEUR D'INVITATION DU COACH : accès serveur + décisions pures.
 *
 * Textes / médias -> PUT /api/referral/campaigns/{id} (route EXISTANTE, liste blanche).
 * Événement / tarifs / règle membres -> PUT /api/referral/campaigns-edition/{id}/evenement
 * (simulation sans écriture, confirmation exigée si des participants existent).
 * Médias du coach -> GET /api/referral/campaigns-medias ; import en morceaux par la route
 * existante /api/coach/upload-chunk, puis empreinte calculée PAR LE SERVEUR (doublon -> le
 * fichier déjà importé est réutilisé). Auth : intercepteur axios global (JWT coach).
 */
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;
export const TAILLE_MORCEAU = 4 * 1024 * 1024;
export const MEDIA_MAX_OCTETS = { video: 200 * 1024 * 1024, audio: 30 * 1024 * 1024 };

export const LIBELLES_TYPE = { trial: 'Essai gratuit', pass_duo: 'Pass Duo', event_free: 'Événement gratuit', event_paid: 'Événement payant' };
export const LIBELLES_STATUT = { draft: 'Brouillon', active: 'Active', hidden: 'Masquée', archived: 'Archivée' }; // V610h : masquée

export function listerInvitations(archivees = false) {
  return axios.get(`${API}/referral/campaigns`, { params: archivees ? { include_archived: 1 } : {}, timeout: 20000 })
    .then((r) => ((r && r.data && Array.isArray(r.data.items)) ? r.data.items : []));
}
export function lireEdition(id) {
  return axios.get(`${API}/referral/campaigns-edition/${encodeURIComponent(id)}`, { timeout: 20000 }).then((r) => r.data);
}
export function enregistrerInvitation(id, corps) {
  return axios.put(`${API}/referral/campaigns/${encodeURIComponent(id)}`, corps, { timeout: 20000 }).then((r) => r.data);
}
export function enregistrerEvenement(id, corps) {
  return axios.put(`${API}/referral/campaigns-edition/${encodeURIComponent(id)}/evenement`, corps, { timeout: 20000 }).then((r) => r.data);
}
export function archiverInvitation(id) {
  return axios.post(`${API}/referral/campaigns/${encodeURIComponent(id)}/archive`, {}, { timeout: 20000 }).then((r) => r.data);
}
// V610h — hors ligne SANS rien supprimer / remise en ligne (mêmes ids, même lien).
export function masquerInvitation(id) {
  return axios.post(`${API}/referral/campaigns/${encodeURIComponent(id)}/masquer`, {}, { timeout: 20000 }).then((r) => r.data);
}
export function reactiverInvitation(id) {
  return axios.post(`${API}/referral/campaigns/${encodeURIComponent(id)}/reactiver`, {}, { timeout: 20000 }).then((r) => r.data);
}
export function lireChaine(id) {
  return axios.get(`${API}/referral/campaigns-relais/${encodeURIComponent(id)}/chaine`, { timeout: 20000 }).then((r) => r.data);
}
export function lireMediasCoach(type) {
  return axios.get(`${API}/referral/campaigns-medias`, { params: { type }, timeout: 20000 })
    .then((r) => ((r && r.data && Array.isArray(r.data.items)) ? r.data.items : []));
}

/** Le genre d'un fichier choisi, ou '' s'il n'est pas accepté pour ce champ. */
export function genreFichier(fichier, attendu) {
  const t = String((fichier && fichier.type) || '');
  if (attendu === 'video' && /^video\/(mp4|webm|quicktime)$/.test(t)) return 'video';
  if (attendu === 'audio' && /^audio\/(mpeg|mp3|mp4|aac|wav|ogg)$/.test(t)) return 'audio';
  return '';
}

/** Import d'un média (vidéo / audio) : morceaux de 4 Mo, puis empreinte serveur. */
export async function importerMedia(fichier, type, surProgression) {
  if (!genreFichier(fichier, type)) throw new Error(type === 'video' ? 'Choisis une vidéo MP4, WebM ou MOV.' : 'Choisis un fichier audio (MP3, M4A, WAV, OGG).');
  if (fichier.size > (MEDIA_MAX_OCTETS[type] || 0)) throw new Error(`Fichier trop lourd (${Math.round((MEDIA_MAX_OCTETS[type] || 0) / 1048576)} Mo maximum).`);
  const total = Math.max(1, Math.ceil(fichier.size / TAILLE_MORCEAU));
  const id = `inv${type}${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
  let fin = null;
  for (let i = 0; i < total; i += 1) {
    const f = new FormData();
    f.append('file', fichier.slice(i * TAILLE_MORCEAU, (i + 1) * TAILLE_MORCEAU), fichier.name);
    f.append('upload_id', id); f.append('chunk_index', String(i)); f.append('total_chunks', String(total));
    f.append('original_name', fichier.name); f.append('content_type', fichier.type); f.append('asset_type', type);
    // eslint-disable-next-line no-await-in-loop
    const r = await axios.post(`${API}/coach/upload-chunk`, f, { timeout: 120000 });
    if (surProgression) surProgression(Math.round(((i + 1) / total) * 100));
    fin = r && r.data;
  }
  if (!fin || !fin.url) throw new Error("L'import n'a pas abouti. Réessaie.");
  const e = await axios.post(`${API}/referral/campaigns-medias/enregistrer`, { url: fin.url }, { timeout: 60000 });
  return { url: (e && e.data && e.data.url) || fin.url, doublon: !!(e && e.data && e.data.doublon) };
}

/** Les champs ÉVÉNEMENT réellement modifiés (comparés à ce que le serveur a rendu). */
export function changementsEvenement(form, evt) {
  if (!evt) return {};
  const c = {};
  if (evt.date_modifiable && form.date && form.date !== evt.date) c.date = form.date;
  if (evt.date_modifiable && form.heure && form.heure !== evt.heure) c.heure = form.heure;
  if (String(form.lieu || '').trim() && String(form.lieu).trim() !== String(evt.lieu || '')) c.lieu = String(form.lieu).trim();
  const t = evt.tarifs;
  if (t) {
    [['prevente', 'prevente'], ['standard', 'standard'], ['derniere_minute', 'derniere_minute']].forEach(([k, src]) => {
      const v = Number(form[k]);
      if (form[k] !== '' && form[k] != null && Number.isFinite(v) && v !== Number(t[src])) c[k] = v;
    });
    if (form.fin_prevente && form.fin_prevente !== t.fin_prevente) c.fin_prevente = form.fin_prevente;
    if (form.fin_standard && form.fin_standard !== t.fin_standard) c.fin_standard = form.fin_standard;
  }
  if (evt.membres && typeof form.membres_actif === 'boolean' && form.membres_actif !== evt.membres.actif) c.gratuit_membres_actif = form.membres_actif;
  return c;
}

/** Un changement « sensible » (date, heure, lieu, prix) demande une confirmation s'il y a des inscrits. */
export function estSensible(changements) {
  return ['date', 'heure', 'lieu', 'prevente', 'standard', 'derniere_minute', 'fin_prevente', 'fin_standard', 'gratuit_membres_actif']
    .some((k) => Object.prototype.hasOwnProperty.call(changements || {}, k));
}

/** Contrôle client des tarifs (le serveur revalide tout). Rend un message ou ''. */
export function erreurTarifs(form, evt) {
  if (!evt || !evt.tarifs) return '';
  for (const k of ['prevente', 'standard', 'derniere_minute']) {
    const v = Number(form[k]);
    if (!Number.isFinite(v) || v <= 0) return 'Les trois tarifs doivent être des montants positifs (CHF).';
  }
  const debut = `${form.date || evt.date}T${form.heure || evt.heure}`;
  if (form.fin_prevente && form.fin_standard && !(form.fin_prevente <= form.fin_standard && form.fin_standard <= debut)) {
    return 'La prévente doit finir avant le tarif standard, qui finit au plus tard au début de l’événement.';
  }
  return '';
}

const JOURS = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'];
const MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];
/** « mercredi 28 octobre · 18h45 » depuis « 2026-10-28T18:45 ». */
export function quandLisible(local) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(String(local || ''));
  if (!m) return '';
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 12);
  return `${JOURS[d.getDay()]} ${d.getDate()} ${MOIS[d.getMonth()]} · ${Number(m[4])}h${m[5]}`;
}

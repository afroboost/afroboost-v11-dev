// ═══════════════════════════════════════════════════════════════════════════
// V534 — PARRAINAGE / PASS DUO : LE SOCLE FRONT, EN UN SEUL ENDROIT
// ═══════════════════════════════════════════════════════════════════════════
//
// POURQUOI CE MODULE. Le Centre Parrainage a QUATRE portes d'entrée (espace
// abonné, mini-carte du chat, ligne après réservation, page /parrainage) et
// une page publique (/duo/<token>). Chacune a besoin des mêmes trois choses :
// « le programme est-il ouvert ? », « qui est le parrain ? » et « comment
// partager ? ». Les écrire quatre fois, c'est les voir diverger quatre fois.
//
// RÈGLES TENUES ICI :
//   - `parrainageActifCache()` est SYNCHRONE et ne fait AUCUN réseau : c'est
//     la seule lecture autorisée dans le ChatWidget (zéro appel au montage) ;
//   - `lireConfigParrainage()` fait UN appel, mutualisé (un seul en vol), avec
//     un cache localStorage de 10 min ; elle ne lève jamais ;
//   - l'identité du parrain vient d'un JETON (espace ou appareil), jamais d'un
//     code dans le corps, jamais de X-User-Email (contrat §5) ;
//   - aucun `?ref=` : le lien d'invitation est celui que le serveur fabrique.
import axios from 'axios';
import { lireSession } from './espaceSession';
import { copyToClipboard } from './clipboard';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
export const API_PARRAINAGE = `${BACKEND_URL}/api/referral`;

/** Clé du cache de configuration : `{enabled, courses, ts}`. */
export const CLE_CACHE_PARRAINAGE = 'afroboost_parrainage';
/** Fraîcheur du cache (contrat §7 : 10 min). */
export const FRAICHEUR_CACHE_MS = 10 * 60 * 1000;

/** Libellés front des états d'un pass (contrat §4). */
export const LIBELLES_STATUT = {
  locked: 'Verrouillé',
  waiting: 'En attente de ton ami',
  friend_registered: 'Ami inscrit',
  unlocked: 'Débloqué',
  used: 'Participation validée',
  expired: 'Expiré',
  cancelled: 'Annulé',
};

/** Les états dans lesquels un pass est encore « vivant » pour le parrain. */
export const STATUTS_OUVERTS = ['locked', 'waiting', 'friend_registered', 'unlocked'];

/** Étape du stepper à 4 crans : Verrouillé → En attente → Ami inscrit → Débloqué. */
export function etapePass(status) {
  switch (status) {
    case 'waiting': return 1;
    case 'friend_registered': return 2;
    case 'unlocked':
    case 'used': return 3;
    default: return 0;
  }
}

// ── Cache de configuration ──────────────────────────────────────────────────

function _lireBrut() {
  try {
    const brut = window.localStorage.getItem(CLE_CACHE_PARRAINAGE);
    if (!brut) return null;
    const j = JSON.parse(brut);
    if (!j || typeof j !== 'object') return null;
    return {
      enabled: !!j.enabled,
      courses: Array.isArray(j.courses) ? j.courses : [],
      ts: Number(j.ts) || 0,
    };
  } catch (e) {
    return null; // mode privé, quota, JSON corrompu : comme s'il n'y avait rien
  }
}

function _ecrire(config) {
  try {
    window.localStorage.setItem(CLE_CACHE_PARRAINAGE, JSON.stringify({
      enabled: !!config.enabled,
      courses: Array.isArray(config.courses) ? config.courses : [],
      ts: Date.now(),
    }));
  } catch (e) { /* stockage indisponible : on vivra sans cache */ }
}

/** Le cache tel quel (même périmé), ou null. Lecture pure. */
export function lireCacheParrainage() {
  return _lireBrut();
}

/**
 * Le programme est-il ouvert, d'après le CACHE seulement ? Synchrone, zéro
 * réseau. Un cache absent ou périmé répond « non » : mieux vaut cacher une
 * carte quelques minutes que lancer une requête depuis le ChatWidget.
 */
export function parrainageActifCache() {
  const c = _lireBrut();
  if (!c || !c.enabled) return false;
  return (Date.now() - c.ts) < FRAICHEUR_CACHE_MS;
}

/** Ce cours est-il éligible au Pass Duo, d'après le cache ? Synchrone. */
export function coursDuoEnCache(courseId) {
  if (!courseId) return false;
  const c = _lireBrut();
  if (!c || !c.enabled) return false;
  return c.courses.some((x) => x && String(x.id) === String(courseId));
}

let _enVol = null; // une seule requête de configuration à la fois

/**
 * La configuration `{enabled, courses}`. Cache de 10 min, un seul appel en
 * vol, jamais d'exception : en cas d'échec réseau on renvoie le cache (même
 * périmé) ou `{enabled:false, courses:[]}` — le programme se ferme, il ne
 * plante pas.
 * @param {boolean} force ignorer la fraîcheur du cache
 */
export function lireConfigParrainage(force) {
  const c = _lireBrut();
  if (!force && c && (Date.now() - c.ts) < FRAICHEUR_CACHE_MS) {
    return Promise.resolve({ enabled: c.enabled, courses: c.courses });
  }
  if (_enVol) return _enVol;
  _enVol = axios.get(`${API_PARRAINAGE}/config`, { timeout: 6000 })
    .then((r) => {
      const d = (r && r.data) || {};
      const config = { enabled: !!d.enabled, courses: Array.isArray(d.courses) ? d.courses : [] };
      _ecrire(config);
      return config;
    })
    .catch(() => {
      const ancien = _lireBrut();
      return ancien ? { enabled: ancien.enabled, courses: ancien.courses } : { enabled: false, courses: [] };
    })
    .finally(() => { _enVol = null; });
  return _enVol;
}

/** Pour les tests : oublier le cache et l'appel en vol. */
export function _resetParrainagePourTest() {
  _enVol = null;
  try { window.localStorage.removeItem(CLE_CACHE_PARRAINAGE); } catch (e) { /* ignore */ }
}

// ── Identité du parrain ─────────────────────────────────────────────────────

/**
 * L'en-tête qui identifie le parrain (contrat §5) : le jeton d'ESPACE
 * (`x-espace-token`) s'il existe, sinon le jeton d'APPAREIL
 * (`X-Subscriber-Token`), sinon `{}` — et le serveur répondra 403.
 * Jamais X-User-Email, jamais un code en clair.
 */
export function enteteParrain() {
  const espace = lireSession();
  if (espace && espace.token) return { 'x-espace-token': espace.token };
  try {
    const tok = window.localStorage.getItem('afroboost_subscriber_token');
    if (tok) return { 'X-Subscriber-Token': tok };
  } catch (e) { /* ignore */ }
  return {};
}

/** Une identité de parrain existe-t-elle côté navigateur ? (sans réseau) */
export function aUneIdentiteParrain() {
  return Object.keys(enteteParrain()).length > 0;
}

/** L'adresse de l'espace abonné de la session courante, ou "" (pour le lien « Ouvre ton espace »). */
export function urlEspaceCourant() {
  const s = lireSession();
  if (!s || !s.code) return '';
  return s.slug
    ? `/espace/${encodeURIComponent(s.code)}?m=${encodeURIComponent(s.slug)}`
    : `/espace/${encodeURIComponent(s.code)}`;
}

// ── Partage ─────────────────────────────────────────────────────────────────

/** Lien WhatsApp « texte prêt » — le texte vient du serveur (`whatsapp_text`). */
export function lienWhatsApp(texte) {
  return `https://wa.me/?text=${encodeURIComponent(texte || '')}`;
}

/** Copie robuste (API moderne puis repli execCommand). Renvoie true/false. */
export function copier(texte) {
  return copyToClipboard(texte || '').then((r) => !!(r && r.success)).catch(() => false);
}

/**
 * Partage natif (`navigator.share`) avec repli sur la copie.
 * @returns {Promise<{ok:boolean, methode:'share'|'copie'|'none'}>}
 */
export function partager({ title, text, url }) {
  if (typeof navigator !== 'undefined' && typeof navigator.share === 'function') {
    return navigator.share({ title, text, url })
      .then(() => ({ ok: true, methode: 'share' }))
      .catch((e) => {
        // Annulation par la personne : ce n'est pas un échec, on ne copie pas.
        if (e && e.name === 'AbortError') return { ok: false, methode: 'none' };
        return copier(url || text).then((ok) => ({ ok, methode: ok ? 'copie' : 'none' }));
      });
  }
  return copier(url || text).then((ok) => ({ ok, methode: ok ? 'copie' : 'none' }));
}

// ── Libellés de séance ──────────────────────────────────────────────────────

const FUSEAU = 'Europe/Zurich';

function _majuscule(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

/** Instant d'une occurrence ISO (naïve = heure suisse), ou NaN. */
function _instant(iso) {
  if (typeof iso !== 'string' || !iso.trim()) return NaN;
  const brut = iso.trim();
  if (/(Z|[+-]\d{2}:?\d{2})$/.test(brut)) return Date.parse(brut);
  // Date naïve lue comme suisse : on la lit en UTC puis on retire le décalage.
  const commeUtc = Date.parse(brut.slice(0, 19) + 'Z');
  if (Number.isNaN(commeUtc)) return NaN;
  try {
    const parts = {};
    new Intl.DateTimeFormat('en-US', {
      timeZone: FUSEAU, hour12: false,
      year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
    }).formatToParts(new Date(commeUtc)).forEach((p) => { parts[p.type] = p.value; });
    const relu = Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day),
      Number(parts.hour) % 24, Number(parts.minute), Number(parts.second));
    if (Number.isNaN(relu)) return NaN;
    return commeUtc - (relu - commeUtc);
  } catch (e) {
    return Date.parse(brut);
  }
}

/** « Dimanche 27 sept. » (jour + date, heure suisse) ; "" si illisible. */
export function libelleJour(iso) {
  const t = _instant(iso);
  if (Number.isNaN(t)) return '';
  try {
    return _majuscule(new Intl.DateTimeFormat('fr-FR', {
      timeZone: FUSEAU, weekday: 'long', day: 'numeric', month: 'short',
    }).format(new Date(t)));
  } catch (e) { return ''; }
}

/** « 18:30 » (heure suisse) ; "" si illisible. */
export function libelleHeure(iso) {
  const t = _instant(iso);
  if (Number.isNaN(t)) return '';
  try {
    return new Intl.DateTimeFormat('fr-FR', { timeZone: FUSEAU, hour: '2-digit', minute: '2-digit', hour12: false })
      .format(new Date(t)).replace('h', ':');
  } catch (e) { return ''; }
}

/**
 * « Dimanche 27 sept. · 18:30 — Bord du Lac, Auvernier » — le libellé du
 * sélecteur de séance et des cartes. Le lieu est facultatif.
 */
export function libelleOccurrence(iso, locationName) {
  const jour = libelleJour(iso);
  const heure = libelleHeure(iso);
  const quand = [jour, heure].filter(Boolean).join(' · ');
  if (!quand) return locationName || '';
  return locationName ? `${quand} — ${locationName}` : quand;
}

/** « 20 sept. » pour l'historique. */
export function libelleDateCourte(iso) {
  const t = _instant(iso);
  if (Number.isNaN(t)) return '';
  try {
    return new Intl.DateTimeFormat('fr-FR', { timeZone: FUSEAU, day: 'numeric', month: 'short' }).format(new Date(t));
  } catch (e) { return ''; }
}

/** Le pass « courant » : le plus récent parmi les ouverts, sinon null. */
export function passCourant(passes) {
  if (!Array.isArray(passes)) return null;
  const ouverts = passes.filter((p) => p && STATUTS_OUVERTS.indexOf(p.status) >= 0);
  if (!ouverts.length) return null;
  return ouverts.slice().sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))[0];
}

// ── Messages de refus (page publique /duo) ──────────────────────────────────

/** Le message FR d'un refus 409 lu dans `X-Refus-Raison`. */
export function messageRefus(raison) {
  switch (String(raison || '')) {
    case 'auto_parrainage':
      return "C'est ton lien : partage-le à un ami (tu ne peux pas être ton propre invité).";
    case 'deja_filleul_occurrence':
      return 'Tu es déjà inscrit à cette séance avec un autre Pass Duo.';
    case 'free_trial_already_used':
    case 'free_trial_already_granted':
      return "Tu as déjà profité de l'essai gratuit Afroboost";
    case 'abonne_actif':
      return 'Tu es déjà membre : réserve directement depuis ton espace';
    case 'pass_ferme':
      return "Ce Pass Duo n'est plus ouvert.";
    default:
      return "Inscription impossible pour le moment. Réessaie dans un instant.";
  }
}

/** Le message FR d'une erreur HTTP de la page publique (hors 409). */
export function messageErreurInvitation(status) {
  if (status === 404) return 'Invitation introuvable';
  if (status === 410) return 'Cette invitation a expiré';
  return 'Invitation indisponible';
}

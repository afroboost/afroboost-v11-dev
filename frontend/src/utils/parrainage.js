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
    // V558 : l'essai gratuit est UNE FOIS PAR PERSONNE, à vie — on le dit clairement.
    case 'free_trial_already_used':
      return 'Tu as déjà utilisé ton essai gratuit.';
    case 'free_trial_already_granted':
      return 'Tu as déjà un essai gratuit en attente : il n’y en a qu’un par personne.';
    case 'whatsapp_requis':
      return 'Indique ton numéro WhatsApp.';
    case 'abonne_actif':
      return 'Tu es déjà membre : réserve directement depuis ton espace';
    case 'pass_ferme':
      return "Ce Pass Duo n'est plus ouvert.";
    // V556 — la chaîne « boule de neige »
    case 'invitation_requise':
      return "Invite d'abord un ami pour débloquer ton essai gratuit.";
    case 'invitation_autre_appareil': // V556 : celui qui a partagé termine l'inscription
      return TEXTE_AUTRE_APPAREIL;
    case 'chaine_en_attente':
      return "Trop d'invitations attendent encore une inscription avant toi. Réessaie un peu plus tard.";
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

// ── V534b : l'offre du Pass Duo est choisie par le participant ──────────────
//
// L'offre publique est un `OffreDTO` : `{id, name, benefit, price, sessions,
// validity, conditions, recommended}`. Rien de technique n'en sort à l'écran :
// jamais l'`id`, jamais une collection, jamais un type. Le serveur valide
// toujours l'`offer_id` renvoyé — le front ne fait que le choisir.

/** Texte EXACT du serveur (et du contrat) pour un pass déjà utilisé. */
export const TEXTE_OFFRE_UTILISEE = 'Cette offre a déjà été utilisée. Tu peux choisir une autre offre pour une prochaine réservation si elle est disponible.';
/** Message affiché après un 409 `conflit_version` (rechargement puis réaffichage). */
export const TEXTE_OFFRE_CONFLIT = "L'offre a changé entre-temps, revoici les offres";
/** Note sous l'offre d'un pass existant (modèle réel : une offre commune, reçue par l'ami). */
export const NOTE_OFFRE_PASS = 'Ton ami la reçoit à son inscription ; ta place vient de ton forfait.';

/** « Offerte » si le prix est 0 (ou absent), sinon « 30 CHF ». */
export function libelleOffre(o) {
  const prix = Number(o && o.price);
  if (!o || !Number.isFinite(prix) || prix <= 0) return 'Offerte';
  return `${Number.isInteger(prix) ? prix : prix.toFixed(2)} CHF`;
}

/** L'avantage lisible d'une offre : `benefit` du serveur, sinon déduit de `sessions`. */
export function avantageOffre(o) {
  if (!o) return '';
  if (o.benefit) return String(o.benefit);
  const n = Number(o.sessions);
  if (Number.isFinite(n) && n > 0) return n === 1 ? '1 séance offerte' : `${n} séances offertes`;
  return '';
}

/**
 * L'offre d'un pass : `pass.offer` (OffreDTO) si le serveur l'envoie, sinon
 * `pass.offer_snapshot` mis au même format, sinon null (pass antérieur à V534b).
 */
export function offreDuPass(pass) {
  if (!pass) return null;
  if (pass.offer && typeof pass.offer === 'object' && pass.offer.name) return pass.offer;
  const s = pass.offer_snapshot;
  if (s && typeof s === 'object' && s.name) {
    return {
      id: s.id || pass.offer_id || '',
      name: s.name,
      benefit: s.benefit || avantageOffre(s),
      price: Number(s.price) || 0,
      sessions: s.sessions,
      validity: s.validity || null,
      conditions: s.conditions || null,
      recommended: false,
    };
  }
  return null;
}

/** Le catalogue courant d'un pass ou d'un cours : toujours un tableau. */
export function offresDe(objet) {
  return objet && Array.isArray(objet.offers) ? objet.offers.filter((o) => o && o.id && o.name) : [];
}

/**
 * L'offre à présélectionner dans un catalogue : la recommandée (`recommended`
 * ou `default_offer_id`) ; une seule offre → celle-là ; sinon aucune (null),
 * et le bouton reste désactivé tant que rien n'est choisi.
 */
export function offrePreselectionnee(offres, defaultOfferId) {
  const liste = Array.isArray(offres) ? offres : [];
  if (liste.length === 1) return liste[0].id;
  const reco = liste.find((o) => o && (o.recommended === true || (defaultOfferId && String(o.id) === String(defaultOfferId))));
  return reco ? reco.id : null;
}

/** Un pass peut-il encore changer d'offre côté client ? (le serveur tranche toujours) */
export function offreModifiable(status) {
  return ['locked', 'waiting', 'friend_registered', 'unlocked'].indexOf(status) >= 0;
}

/**
 * `PATCH /api/referral/pass/{cible}/offer {offer_id, version}`.
 * `cible` = l'`id` du pass (parrain, en-têtes `enteteParrain()`) ou le
 * `share_token` (public, avant inscription). Renvoie la promesse axios telle
 * quelle : l'appelant lit le PassDTO ou le 409 (`X-Refus-Raison`).
 */
export function changerOffre({ passId, token, offerId, version, headers }) {
  const cible = encodeURIComponent(passId || token || '');
  return axios.patch(
    `${API_PARRAINAGE}/pass/${cible}/offer`,
    { offer_id: offerId, version: Number(version) || 1 },
    { headers: headers || {}, timeout: 15000 },
  );
}

/**
 * V539 — Changer la SÉANCE d'un Pass Duo (avant l'inscription de l'ami) :
 * `PATCH /api/referral/pass/{cible}/occurrence {occurrence, version}`.
 * Même forme que `changerOffre`, mêmes deux portes (parrain par `id` avec
 * en-têtes, ami par `share_token` sans jeton). L'occurrence envoyée vient
 * TOUJOURS de la liste rendue par le serveur : le serveur la revérifie.
 */
export function changerSeance({ passId, token, occurrence, version, headers }) {
  const cible = encodeURIComponent(passId || token || '');
  return axios.patch(
    `${API_PARRAINAGE}/pass/${cible}/occurrence`,
    { occurrence: String(occurrence || ''), version: Number(version) || 1 },
    { headers: headers || {}, timeout: 15000 },
  );
}

/**
 * V539 — Les occurrences du serveur, au format attendu par `SessionsModal`
 * (`{id, nom, lieu, quand: Date, ponctuel, offres}`). Fonction pure : elle ne
 * lit rien d'autre que ce qu'on lui donne, et écarte les dates illisibles.
 */
export function occurrencesPourCalendrier(occurrences, course) {
  const c = course || {};
  return (Array.isArray(occurrences) ? occurrences : [])
    .map((o) => {
      const iso = typeof o === 'string' ? o : (o && (o.occurrence || o.datetime));
      const d = iso ? new Date(String(iso).length <= 10 ? `${iso}T00:00:00` : iso) : null;
      if (!d || Number.isNaN(d.getTime())) return null;
      return {
        id: c.id || 'duo',
        nom: c.name || 'Séance Afroboost',
        lieu: c.locationName || c.location || '',
        quand: d,
        iso: String(iso),
        ponctuel: false,
        offres: [],
      };
    })
    .filter(Boolean)
    .sort((a, b) => a.quand - b.quand);
}

/** `{status, raison, detail}` d'une erreur axios (raison = en-tête `X-Refus-Raison`). */
export function lireRefus(err) {
  const rep = (err && err.response) || {};
  const h = rep.headers || {};
  const d = rep.data;
  return {
    status: rep.status || 0,
    raison: String(h['x-refus-raison'] || h['X-Refus-Raison'] || (d && d.code) || ''),
    detail: d && typeof d.detail === 'string' ? d.detail : '',
  };
}

/** Le message FR d'un changement d'offre refusé (hors conflit de version, géré par l'appelant). */
export function messageRefusOffre(refus, status) {
  const r = refus || {};
  if (r.status === 409 && r.raison === 'pass_non_modifiable') return r.detail || (status === 'used' ? TEXTE_OFFRE_UTILISEE : 'Ce Pass ne peut plus changer d’offre.');
  if (r.status === 409 && r.raison === 'pass_deja_rejoint') return 'Un ami a déjà rejoint ce Pass : seul le parrain peut encore changer l’offre.';
  if (r.status === 400) return 'Cette offre n’est plus disponible pour cette séance. Choisis-en une autre.';
  if (r.status === 429) return 'Trop de tentatives. Réessaie dans un instant.';
  if (r.status === 401 || r.status === 403) return 'Ouvre ton espace abonné pour changer d’offre.';
  return 'Changement impossible pour le moment. Réessaie dans un instant.';
}

/** Ligne d'historique « Offre modifiée : A → B ». */
export function libelleChangementOffre(e) {
  const de = (e && (e.from_name || e.from)) || '';
  const vers = (e && (e.to_name || e.to)) || '';
  if (de && vers) return `Offre modifiée : ${de} → ${vers}`;
  if (vers) return `Offre choisie : ${vers}`;
  return 'Offre modifiée';
}

/**
 * L'historique à afficher : `history[]` du serveur, complété des lignes
 * `offer_history[]` des passes quand le serveur n'a pas produit de ligne
 * `offer_changed`. Récents d'abord, comme le serveur.
 */
export function lignesHistorique(history, passes) {
  const base = (Array.isArray(history) ? history : []).filter(Boolean).map((h) => (
    h.type === 'offer_changed' && !h.label ? Object.assign({}, h, { label: libelleChangementOffre(h) }) : h
  ));
  if (base.some((h) => h.type === 'offer_changed')) return base;
  const extra = [];
  (Array.isArray(passes) ? passes : []).forEach((p) => {
    (p && Array.isArray(p.offer_history) ? p.offer_history : []).forEach((e) => {
      if (!e) return;
      extra.push({ at: e.changed_at || e.at || '', type: 'offer_changed', label: libelleChangementOffre(e), pass_id: p.id });
    });
  });
  if (!extra.length) return base;
  return base.concat(extra).sort((a, b) => String(b.at || '').localeCompare(String(a.at || '')));
}

// ═══════════════════════════════════════════════════════════════════════════
// V551 — PARRAINAGE V2 : L'INVITATION PERSONNALISÉE (nom, photo, message)
// ═══════════════════════════════════════════════════════════════════════════
//
// Ce que le membre personnalise ici n'appartient QU'À SON INVITATION
// (`pass.invitation`). Aucune fonction de ce bloc n'écrit dans un profil :
// ni /spordate/unified-profile (lu seulement), ni l'abonné. Le jeton de
// partage ne change jamais ; seul `?v=` du `share_url` renvoyé peut bouger.

/** Nom affiché quand aucun vrai prénom n'est disponible (jamais un e-mail). */
// V558 : repli UNIQUEMENT si l'identité est réellement inconnue — jamais « Un membre Afroboost ».
export const NOM_NEUTRE = 'Afroboost';
/** Longueur maximale du message d'invitation (contrat : ≤ 280). */
export const MESSAGE_MAX = 280;
/** Longueur maximale du nom d'invitation (contrat : 1..40). */
export const NOM_MAX = 40;
/** Message intégré du contrat, si le serveur n'en fournit aucun. */
export const MESSAGE_INVITATION_DEFAUT = "Je t'invite à venir essayer Afroboost avec moi. Réserve ta place ici :";

/**
 * Le nom tel qu'on peut l'afficher, ou "" : jamais un e-mail (« @ »), jamais
 * un identifiant technique (aucune lettre, ou ≥ 20 caractères sans espace).
 * Même filtre que le serveur (`nom_affichable`), en plus strict côté front :
 * mieux vaut le nom neutre qu'une adresse affichée à un inconnu.
 */
export function nomAffichable(nom) {
  const s = String(nom == null ? '' : nom).trim();
  if (!s || s.indexOf('@') >= 0) return '';
  if (!/\p{L}/u.test(s)) return '';
  if (s.length >= 20 && !/\s/.test(s)) return '';
  return s.slice(0, NOM_MAX);
}

/** Une photo que le serveur acceptera (contrat PUT /invitation), sinon null. */
export function photoAutorisee(url) {
  const s = String(url || '').trim();
  if (!s || s.length > 500) return null;
  if (/^\/api\/files\//.test(s)) return s;
  const m = /^https:\/\/([^/?#]+)(?:[/?#]|$)/i.exec(s);
  if (!m) return null;
  const hote = m[1].toLowerCase();
  // L0 : res.cloudinary.com (https seulement) — beaucoup de photos de profil y vivent.
  return ['afroboost.com', 'firebasestorage.googleapis.com', 'storage.googleapis.com', 'lh3.googleusercontent.com', 'res.cloudinary.com']
    .indexOf(hote) >= 0 ? s : null;
}

/** Message borné à 280 caractères (le compteur l'affiche, le serveur revérifie). */
export function bornerMessage(texte) {
  return String(texte == null ? '' : texte).slice(0, MESSAGE_MAX);
}

/**
 * Le contexte de séance/offre passé à /parrainage (`?course=&occurrence=&offer=`),
 * ou des chaînes vides. Lecture pure de l'URL courante.
 */
export function lireContexteUrl(search) {
  let q;
  try {
    q = new URLSearchParams(search != null ? search : (window.location.search || ''));
  } catch (e) {
    return { course: '', occurrence: '', offer: '' };
  }
  return {
    course: q.get('course') || '',
    occurrence: q.get('occurrence') || '',
    offer: q.get('offer') || '',
  };
}

/**
 * Invitation du coach (page Campagnes) : le jeton `?campagne=<token>` porté
 * par le lien /parrainage, ou "" (absent ou illisible). Lecture pure.
 */
export function lireCampagneUrl(search) {
  let q;
  try {
    q = new URLSearchParams(search != null ? search : (window.location.search || ''));
  } catch (e) {
    return '';
  }
  const k = String(q.get('campagne') || '').trim();
  return /^[A-Za-z0-9_-]{1,128}$/.test(k) ? k : '';
}

/**
 * Le corps de création d'un pass avec `referral_campaign` SEULEMENT si un
 * jeton de campagne existe : sans jeton, le corps est rendu tel quel (même
 * objet) — strictement rien ne change pour le parcours habituel.
 */
export function avecCampagne(corps, campagne) {
  const k = String(campagne || '').trim();
  if (!k) return corps;
  return Object.assign({}, corps, { referral_campaign: k });
}

/**
 * Lit ce qu'il faut pour préremplir l'invitation, en UN aller-retour parallèle :
 *   - `GET /api/referral/invitation` → { identity, default_message, pass } ;
 *   - `GET /api/spordate/unified-profile/me` → { lie, profil } (lecture seule).
 * Ne lève jamais : un échec donne des valeurs vides, et le front retombe sur
 * le nom neutre et le message intégré.
 */
export function lireInvitation(headers) {
  const h = headers || enteteParrain();
  const inv = axios.get(`${API_PARRAINAGE}/invitation`, { headers: h, timeout: 10000 })
    .then((r) => (r && r.data) || {}).catch(() => ({}));
  const prof = axios.get(`${BACKEND_URL}/api/spordate/unified-profile/me`, { headers: h, timeout: 10000 })
    .then((r) => (r && r.data) || {}).catch(() => ({}));
  return Promise.all([inv, prof]).then(([i, p]) => ({
    identity: (i && i.identity) || {},
    default_message: (i && typeof i.default_message === 'string') ? i.default_message : '',
    pass: (i && i.pass && i.pass.id) ? i.pass : null,
    image_url: (i && (i.image_url || (i.effective && i.effective.image_url))) || '',
    lie: !!(p && p.lie),
    profil: (p && p.lie && p.profil) || null,
  }));
}

/**
 * Identité PRÉREMPLIE de l'invitation : l'override déjà posé sur le pass,
 * sinon le profil Spordateur lié, sinon l'identité renvoyée par /invitation,
 * sinon rien (le front affichera NOM_NEUTRE et l'initiale).
 * @returns {{nom:string, photo:(string|null)}}
 */
export function identitePreremplie({ pass, profil, identity }) {
  const inv = pass && pass.invitation;
  const versionPosee = !!(inv && Number(inv.version) > 0);
  const nomPass = inv ? nomAffichable(inv.display_name) : '';
  const nomProfil = profil ? nomAffichable(profil.displayName) : '';
  const nomIdentite = identity ? nomAffichable(identity.display_name) : '';
  const nom = nomPass || nomProfil || nomIdentite || '';
  let photo = null;
  if (versionPosee) {
    photo = photoAutorisee(inv.photo_url); // null = le membre l'a retirée : on respecte
  } else {
    const photoProfil = profil ? (profil.photoURL || (Array.isArray(profil.photos) ? profil.photos[0] : '')) : '';
    photo = photoAutorisee(photoProfil) || photoAutorisee(identity && identity.photo_url);
  }
  return { nom, photo };
}

/** Le message prérempli : celui du pass s'il existe, sinon celui du coach, sinon l'intégré. */
export function messagePrerempli({ pass, default_message }) {
  const inv = pass && pass.invitation;
  if (inv && typeof inv.message === 'string' && inv.message.trim()) return bornerMessage(inv.message);
  if (typeof default_message === 'string' && default_message.trim()) return bornerMessage(default_message);
  return MESSAGE_INVITATION_DEFAUT;
}

/** L'objet `invitation` du contrat (POST /pass et PUT /invitation). */
export function corpsInvitation({ nom, photo, message }) {
  const n = nomAffichable(nom);
  const corps = { photo_url: photoAutorisee(photo), message: bornerMessage(message).trim() || null };
  if (n) corps.display_name = n;
  return corps;
}

/** `PUT /api/referral/pass/{id}/invitation` — même jeton, nouveau `?v=` possible. */
export function modifierInvitation({ passId, invitation, headers }) {
  return axios.put(`${API_PARRAINAGE}/pass/${encodeURIComponent(passId)}/invitation`, invitation,
    { headers: headers || enteteParrain(), timeout: 10000 });
}

/** Le texte WhatsApp : celui du serveur s'il porte le lien partagé, sinon message + lien. */
export function texteWhatsAppInvitation(pass, message) {
  const url = (pass && (pass.share_url || pass.invite_url)) || '';
  const serveur = pass && pass.whatsapp_text;
  if (serveur && url && serveur.indexOf(url) >= 0) return serveur;
  const m = String(message || '').trim();
  return m ? `${m}\n${url}` : `Rejoins mon Pass Duo Afroboost : ${url}`;
}


// ═══════════════════════════════════════════════════════════════════════════
// V556 — PARRAINAGE V3 « BOULE DE NEIGE » : L'INVITATION ENFANT DU FILLEUL
// ═══════════════════════════════════════════════════════════════════════════
//
// Le filleul (page /duo/<T0>) prépare puis PARTAGE une invitation enfant (T1)
// AVANT de pouvoir s'inscrire. Toutes les routes sont publiques par jeton :
//   POST  /pass/{T0}/chain         crée (201 + edit_key) ou rend (200) l'enfant ;
//   PATCH /pass/{T0}/chain         modifie prénom / message (en-tête X-Chain-Key) ;
//   POST  /pass/{T0}/chain/share   enregistre que le partage a été DÉCLENCHÉ
//                                  (rend le PROCHAIN share_url) ;
//   GET   /pass/{T0}/chain/preview relance le contrôle d'aperçu.
// « Partagée » = l'action de partage a été déclenchée ; jamais « envoyée ».

/** Message par défaut de la carte du filleul (texte du message, pas une icône). */
/** V556 — le visiteur revient d'un AUTRE appareil que celui qui a partagé. */
export const TEXTE_AUTRE_APPAREIL = "Pour protéger ton invitation, termine l'inscription sur l'appareil avec lequel tu as partagé ton invitation.";

export const MESSAGE_CHAINE_DEFAUT = "Je t'invite à venir découvrir Afroboost avec moi 👇";

/** Clé localStorage de la clé d'édition de l'invitation enfant du pass `token`. */
export function cleChaine(token) {
  return `afroboost_chaine_${token || ''}`;
}

/** La clé d'édition gardée pour ce pass, ou "" (stockage indisponible = pas de clé). */
export function lireCleChaine(token) {
  try { return window.localStorage.getItem(cleChaine(token)) || ''; } catch (e) { return ''; }
}

/** Garde la clé d'édition (silencieux si le stockage est indisponible). */
export function ecrireCleChaine(token, cle) {
  if (!cle) return;
  try { window.localStorage.setItem(cleChaine(token), String(cle)); } catch (e) { /* mode privé : pas d'édition au retour */ }
}

function _corpsChaine({ display_name, message }) {
  const corps = {};
  const n = nomAffichable(display_name);
  if (n) corps.display_name = n;
  const m = bornerMessage(message).trim();
  if (m) corps.message = m;
  return corps;
}

/** `POST /pass/{token}/chain` — crée ou rend l'invitation enfant (promesse axios). */
export function creerInvitationChaine({ token, display_name, message, kind, course_id, occurrence }) {
  // V558 : le type et la séance CHOISIS pour l'ami partent avec la création ; si
  // l'enfant existe déjà, la clé de CET appareil permet au serveur de les reprendre.
  const corps = _corpsChaine({ display_name, message });
  if (kind) corps.kind = kind;
  if (course_id && occurrence) { corps.course_id = course_id; corps.occurrence = occurrence; }
  const cle = lireCleChaine(token);
  return axios.post(`${API_PARRAINAGE}/pass/${encodeURIComponent(token || '')}/chain`,
    corps, { timeout: 20000, headers: cle ? { 'X-Chain-Key': cle } : {} });
}

/** V558 — `GET /pass/{token}/chain/options` → `{types, seances, seance_parent}` (aucune PII). */
export function lireOptionsChaine({ token }) {
  return axios.get(`${API_PARRAINAGE}/pass/${encodeURIComponent(token || '')}/chain/options`, { timeout: 15000 });
}

/** V558 — change la séance (et/ou le type) de l'invitation enfant AVANT son envoi. */
export function choisirSeanceChaine({ token, editKey, kind, course_id, occurrence }) {
  const corps = {};
  if (kind) corps.kind = kind;
  if (course_id && occurrence) { corps.course_id = course_id; corps.occurrence = occurrence; }
  return axios.patch(`${API_PARRAINAGE}/pass/${encodeURIComponent(token || '')}/chain`,
    corps, { headers: { 'X-Chain-Key': editKey || '' }, timeout: 20000 });
}

/**
 * V558 — les séances offrables → le format du calendrier EXISTANT (SessionsModal,
 * `occurrencesFournies`) : une entrée par date, avec le cours, l'heure et le lieu.
 */
export function seancesPourCalendrier(seances) {
  const sortie = [];
  (Array.isArray(seances) ? seances : []).forEach((s) => {
    occurrencesPourCalendrier(s && s.occurrences, {
      id: s && s.course_id, name: s && s.name, locationName: s && s.location,
    }).forEach((o) => sortie.push(o));
  });
  return sortie.sort((a, b) => a.quand - b.quand);
}

/** V558 — le message d'un refus du choix de séance (400 / 409). */
export function messageRefusSeance(refus) {
  const r = refus || {};
  if (r.raison === 'seance_indisponible' || r.raison === 'seance_non_autorisee') return 'Cette séance n’est plus disponible.';
  if (r.raison === 'invitation_deja_partagee') return 'Ton invitation a déjà été envoyée : sa séance ne peut plus changer.';
  if (r.raison === 'type_non_autorise') return 'Cette offre n’est plus proposée. Choisis-en une autre.';
  if (r.status === 403) return 'Cette invitation ne peut être modifiée que depuis l’appareil qui l’a créée.';
  if (r.status === 429) return 'Trop de tentatives. Réessaie dans un instant.';
  return 'La séance n’a pas pu être enregistrée. Réessaie dans un instant.';
}

/**
 * `PATCH /pass/{token}/chain` avec `X-Chain-Key` — même jeton enfant, nouvelle carte.
 * UX-P2 : `photo_url` (URL ou null), `whatsapp` (texte avec indicatif, normalisé
 * par le serveur, 422 si invalide) et `consent_contact` (bool) ne partent QUE
 * s'ils sont fournis (undefined = champ inchangé, jamais écrasé).
 */
export function modifierInvitationChaine({ token, editKey, display_name, message, photo_url, whatsapp, consent_contact }) {
  const corps = _corpsChaine({ display_name, message });
  if (photo_url !== undefined) corps.photo_url = photo_url || null;
  if (whatsapp !== undefined) corps.whatsapp = String(whatsapp || '');
  if (consent_contact !== undefined) corps.consent_contact = !!consent_contact;
  return axios.patch(`${API_PARRAINAGE}/pass/${encodeURIComponent(token || '')}/chain`,
    corps,
    { headers: { 'X-Chain-Key': editKey || '' }, timeout: 20000 });
}

/** UX-P2 — photo de la carte : JPEG / PNG / WebP, 5 Mo au plus (le serveur revérifie). */
export const PHOTO_CHAINE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
export const PHOTO_CHAINE_MAX = 5 * 1024 * 1024;

/** '' si le fichier est acceptable, sinon le message FR du refus. */
export function refusPhotoChaine(file) {
  if (!file) return 'Choisis une photo.';
  if (PHOTO_CHAINE_TYPES.indexOf(String(file.type || '').toLowerCase()) < 0) return 'Choisis une photo JPEG, PNG ou WebP.';
  if (Number(file.size) > PHOTO_CHAINE_MAX) return 'Cette photo dépasse 5 Mo : choisis-en une plus légère.';
  return '';
}

/** UX-P2 — `POST /pass/{token}/chain/photo` (multipart `file`, X-Chain-Key) → `{photo_url}`. */
export function envoyerPhotoChaine({ token, editKey, file }) {
  const fd = new FormData();
  fd.append('file', file);
  return axios.post(`${API_PARRAINAGE}/pass/${encodeURIComponent(token || '')}/chain/photo`,
    fd, { headers: { 'X-Chain-Key': editKey || '' }, timeout: 60000 });
}

/**
 * UX-P2 — indicatifs proposés (Suisse par défaut). La normalisation DÉFINITIVE
 * est faite par le serveur ; ici on assemble seulement « +41 79 123 45 67 ».
 */
export const INDICATIF_DEFAUT = '+41';
export const INDICATIFS = [
  ['+41', 'Suisse'], ['+33', 'France'], ['+49', 'Allemagne'], ['+39', 'Italie'], ['+43', 'Autriche'],
  ['+32', 'Belgique'], ['+352', 'Luxembourg'], ['+34', 'Espagne'], ['+351', 'Portugal'], ['+44', 'Royaume-Uni'],
  ['+225', "Côte d'Ivoire"], ['+221', 'Sénégal'], ['+237', 'Cameroun'], ['+243', 'RD Congo'], ['+242', 'Congo'],
  ['+229', 'Bénin'], ['+228', 'Togo'], ['+223', 'Mali'], ['+226', 'Burkina Faso'], ['+224', 'Guinée'],
  ['+1', 'États-Unis / Canada'],
];

/**
 * Le numéro à envoyer : '' si vide ; tel quel s'il porte déjà un indicatif
 * (« +… » ou « 00… ») ; sinon indicatif + numéro sans le 0 national de tête.
 */
export function numeroWhatsAppChaine(indicatif, numero) {
  const n = String(numero || '').trim();
  if (!/\d/.test(n)) return '';
  if (/^(\+|00)/.test(n)) return n;
  return `${indicatif || INDICATIF_DEFAUT} ${n.replace(/^0+/, '')}`;
}

/** `POST /pass/{token}/chain/share {channel}` — whatsapp | share | share_image | copy. */
export function enregistrerPartageChaine({ token, channel }) {
  // V556 : la clé de l'appareil qui a préparé l'invitation (exigée par le serveur).
  return axios.post(`${API_PARRAINAGE}/pass/${encodeURIComponent(token || '')}/chain/share`,
    { channel }, { headers: { 'X-Chain-Key': lireCleChaine(token) }, timeout: 15000 });
}

/** `GET /pass/{token}/chain/preview` — `{child, shared, preview}`. */
export function santeApercuChaine({ token }) {
  return axios.get(`${API_PARRAINAGE}/pass/${encodeURIComponent(token || '')}/chain/preview`, { timeout: 15000 });
}

function _fetchAvecDelai(url, delaiMs) {
  if (typeof fetch !== 'function') return Promise.reject(new Error('fetch_indisponible'));
  let ctrl = null;
  try { ctrl = typeof AbortController === 'function' ? new AbortController() : null; } catch (e) { ctrl = null; }
  const t = ctrl ? setTimeout(() => { try { ctrl.abort(); } catch (e) { /* ignore */ } }, delaiMs) : null;
  return fetch(url, ctrl ? { method: 'GET', signal: ctrl.signal } : { method: 'GET' })
    .finally(() => { if (t) clearTimeout(t); });
}

function _enTete(rep, nom) {
  try { return (rep && rep.headers && typeof rep.headers.get === 'function' && rep.headers.get(nom)) || ''; } catch (e) { return ''; }
}

/**
 * Contrôle d'aperçu CÔTÉ NAVIGATEUR, avant d'activer les boutons :
 *   - `card_url` → 200 + `content-type: image/*` ; le Blob devient un `File`
 *     (pré-chargé ici pour que `navigator.share({files})` garde le geste) ;
 *   - `share_url` → 200 + HTML portant og:title, og:description, og:image.
 * Ne rejette JAMAIS : un contrôle raté donne `ok:false` (repli « Aperçu
 * simplifié », le partage par lien reste possible).
 * @returns {Promise<{ok:boolean, file:(File|null), checks:object}>}
 */
export function verifierApercuNavigateur({ cardUrl, shareUrl, delaiMs }) {
  const delai = Number(delaiMs) > 0 ? Number(delaiMs) : 8000;
  const checks = { image_ok: false, image_type: '', share_page: false, og_title: false, og_description: false, og_image: false };
  let file = null;
  const image = !cardUrl ? Promise.resolve() : _fetchAvecDelai(cardUrl, delai)
    .then((rep) => {
      const type = String(_enTete(rep, 'content-type') || '').split(';')[0].trim();
      if (!rep || !rep.ok || type.indexOf('image/') !== 0) return undefined;
      checks.image_type = type;
      return rep.blob().then((blob) => {
        if (!blob || !blob.size) return;
        checks.image_ok = true;
        try {
          const ext = type === 'image/png' ? 'png' : (type === 'image/webp' ? 'webp' : 'jpg');
          file = new File([blob], `invitation-afroboost.${ext}`, { type });
        } catch (e) { file = null; }
      });
    })
    .catch(() => undefined);
  const page = !shareUrl ? Promise.resolve() : _fetchAvecDelai(shareUrl, delai)
    .then((rep) => {
      if (!rep || !rep.ok) return undefined;
      checks.share_page = true;
      return rep.text().then((html) => {
        let doc = null;
        try { doc = new DOMParser().parseFromString(String(html || ''), 'text/html'); } catch (e) { doc = null; }
        const og = (prop) => {
          if (doc) {
            const el = doc.querySelector(`meta[property="og:${prop}"], meta[name="og:${prop}"]`);
            return !!(el && String(el.getAttribute('content') || '').trim());
          }
          return new RegExp(`og:${prop}`).test(String(html || ''));
        };
        checks.og_title = og('title');
        checks.og_description = og('description');
        checks.og_image = og('image');
      });
    })
    .catch(() => undefined);
  return Promise.all([image, page]).then(() => ({
    ok: !!(checks.image_ok && checks.share_page && checks.og_title && checks.og_description && checks.og_image),
    file,
    checks,
  }));
}

/** Le texte partagé : message + saut de ligne + lien COURANT. */
export function texteChaine(message, shareUrl) {
  const m = String(message || '').trim();
  return m ? `${m}\n${shareUrl || ''}` : String(shareUrl || '');
}

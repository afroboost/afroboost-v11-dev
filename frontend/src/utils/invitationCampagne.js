// ═══════════════════════════════════════════════════════════════════════════
// INVITATION (page Campagnes du coach) — appels API + fonctions pures
// ═══════════════════════════════════════════════════════════════════════════
//
// Une invitation N'EST PAS une campagne d'envoi : aucun contact, aucun canal,
// aucune programmation, aucun crédit. Le coach prépare une carte (essai
// gratuit, Pass Duo, événement gratuit ou payant), l'enregistre, l'active,
// puis la PARTAGE lui-même (WhatsApp, partage natif, lien, QR).
//
// RÈGLES TENUES ICI :
//   - les corps envoyés ne portent QUE les champs du contrat (liste blanche
//     CHAMPS_CONTENU) : jamais recipients, channel, send_at, scheduledAt,
//     coach_id — le propriétaire est décidé par le serveur (JWT) ;
//   - l'authentification passe par l'intercepteur axios global (App.js :
//     `Authorization: Bearer <afroboost_jwt>`) : aucun en-tête inventé ici ;
//   - toutes les fonctions de ce module, hors appels réseau, sont pures.
import axios from 'axios';
import { texteChaine } from './parrainage';

/** Les quatre types d'invitation, dans l'ordre d'affichage. */
export const TYPES_INVITATION = [
  { id: 'trial', libelle: 'Essai gratuit', aide: 'Offre un premier cours gratuit sur une séance précise.', icone: 'gift' },
  { id: 'pass_duo', libelle: 'Pass Duo', aide: 'Ton invité crée son Pass Duo pour venir avec un ami.', icone: 'users' },
  { id: 'event_free', libelle: 'Événement gratuit', aide: 'Un événement ouvert à tous, inscription gratuite.', icone: 'calendar' },
  { id: 'event_paid', libelle: 'Événement payant', aide: 'Un événement avec billet, aux tarifs de ton offre.', icone: 'ticket' },
];

/** Texte du bouton (CTA) par défaut, par type. */
export const CTA_DEFAUT = {
  trial: 'Réserver mon essai',
  pass_duo: 'Créer mon Pass Duo',
  event_free: "Je m'inscris",
  event_paid: 'Je réserve ma place',
};

/** Titre proposé par défaut, par type (modifiable). */
export const TITRE_DEFAUT = {
  trial: 'Ton premier cours Afroboost est offert',
  pass_duo: 'Viens danser à deux avec le Pass Duo',
  event_free: 'Un événement Afroboost gratuit',
  event_paid: 'Un événement Afroboost à ne pas manquer',
};

export const TITRE_MAX = 80;
export const SOUS_TITRE_MAX = 120;
export const MESSAGE_MAX = 280;
export const CTA_MAX = 30; // le serveur refuse au-delà (422)

/** Texte affiché pour un événement payant tant que l'activation répond 409. */
export const TEXTE_FUSEAU_PALIERS = 'Les événements payants pourront être partagés dès la correction du fuseau horaire des paliers.';
/** Message d'une session expirée / sans jeton (401 / 403). */
export const TEXTE_RECONNEXION = 'Reconnecte-toi pour créer une invitation';

/** Les seuls champs de contenu que le serveur reçoit (liste blanche). */
export const CHAMPS_CONTENU = [
  'type', 'title', 'subtitle', 'message', 'cta_label', 'image_url', 'image_source',
  'course_id', 'occurrence', 'offer_id',
];

/**
 * Racine des URL : accepte `''`, `https://x.ch`, ou une base qui finit déjà
 * par `/api` (CoachDashboard passe `${BACKEND_URL}/api`) — on n'écrit jamais
 * `/api/api/...`.
 */
export function racineApi(API) {
  return String(API || '').replace(/\/+$/, '').replace(/\/api$/, '');
}

// ── Offres, cours, dates ───────────────────────────────────────────────────

/** Une offre est-elle gratuite ? (`is_free`, sinon prix nul ou absent) */
export function offreGratuite(o) {
  if (!o) return false;
  if (typeof o.is_free === 'boolean') return o.is_free;
  const p = Number(o.price);
  return !Number.isFinite(p) || p <= 0;
}

/** Les offres proposables pour un type : gratuites (trial, event_free), payantes (event_paid), aucune (pass_duo). */
export function offresPourType(type, offers) {
  const liste = (Array.isArray(offers) ? offers : []).filter((o) => o && o.id);
  if (type === 'trial' || type === 'event_free') return liste.filter(offreGratuite);
  if (type === 'event_paid') return liste.filter((o) => !offreGratuite(o));
  return [];
}

function _prix(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : null;
}

/** « 30 CHF » / « 12.50 CHF ». */
export function libellePrix(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return '';
  return `${Number.isInteger(v) ? v : v.toFixed(2)} CHF`;
}

/**
 * Les paliers de prix (lecture seule) d'une offre payante : Prévente,
 * Standard, Dernière minute — 3 au plus, dans cet ordre. Sans prix
 * progressif : un seul palier « Prix » (le prix de l'offre).
 */
export function paliersOffre(o) {
  if (!o) return [];
  if (o.has_progressive_pricing) {
    return [
      { cle: 'early_bird', libelle: 'Prévente', prix: _prix(o.price_early_bird) },
      { cle: 'standard', libelle: 'Standard', prix: _prix(o.price_standard) },
      { cle: 'last_minute', libelle: 'Dernière minute', prix: _prix(o.price_last_minute) },
    ].filter((p) => p.prix != null).slice(0, 3);
  }
  const p = _prix(o.price);
  return p != null ? [{ cle: 'prix', libelle: 'Prix', prix: p }] : [];
}

/** « 18:30 » depuis « 18:30 », « 18h30 », « 9:05:00 » ; "" si illisible. */
export function heureDuCours(time) {
  const m = /^\s*(\d{1,2})\s*[:hH.]\s*(\d{2})/.exec(String(time || ''));
  if (!m) return '';
  const h = Number(m[1]);
  const mn = Number(m[2]);
  if (h > 23 || mn > 59) return '';
  return `${String(h).padStart(2, '0')}:${String(mn).padStart(2, '0')}`;
}

/** Date locale « YYYY-MM-DD » d'un objet Date. */
export function dateIso(d) {
  const x = d instanceof Date ? d : new Date();
  return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`;
}

/**
 * Prochaine date (aujourd'hui compris) tombant le jour `weekday`
 * (0 = dimanche … 6 = samedi, convention des cours Afroboost). "" si inconnu.
 */
export function prochaineDate(weekday, aujourdhui) {
  const w = Number(weekday);
  if (weekday === null || weekday === undefined || weekday === '' || !Number.isInteger(w) || w < 0 || w > 6) return '';
  const base = /^\d{4}-\d{2}-\d{2}$/.test(String(aujourdhui || '')) ? new Date(`${aujourdhui}T12:00:00`) : new Date();
  const delta = (w - base.getDay() + 7) % 7;
  const d = new Date(base.getTime());
  d.setDate(d.getDate() + delta);
  return dateIso(d);
}

/** `occurrence` = "YYYY-MM-DDTHH:MM" si date ET heure sont valides, sinon "". */
export function construireOccurrence(date, heure) {
  const d = String(date || '').trim();
  const h = heureDuCours(heure);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d) || !h) return '';
  return `${d}T${h}`;
}

// ── Formulaire → corps ─────────────────────────────────────────────────────

/** Un formulaire vide pour `type` (titre et CTA proposés par défaut). */
export function formulaireInitial(type, dateInitiale) {
  return {
    type: type || '',
    title: type ? (TITRE_DEFAUT[type] || '') : '',
    subtitle: '',
    message: '',
    cta_label: type ? (CTA_DEFAUT[type] || '') : '',
    image_url: '',
    image_source: '',
    course_id: '',
    date: /^\d{4}-\d{2}-\d{2}$/.test(String(dateInitiale || '')) ? String(dateInitiale) : '',
    heure: '',
    offer_id: '',
  };
}

function _texte(v, max) {
  const s = String(v == null ? '' : v).trim();
  return max ? s.slice(0, max) : s;
}

/**
 * Le corps de contenu (liste blanche CHAMPS_CONTENU) : champs sans objet pour
 * le type → null. Jamais recipients / channel / send_at / scheduledAt / coach_id.
 */
export function construireCorps(f) {
  const x = f || {};
  const type = x.type || '';
  const avecCours = TYPES_INVITATION.some((t) => t.id === type); // événements : cours facultatif
  const avecOffre = type === 'trial' || type === 'event_free' || type === 'event_paid';
  const occurrence = construireOccurrence(x.date, x.heure);
  const corps = {
    type,
    title: _texte(x.title, TITRE_MAX),
    subtitle: _texte(x.subtitle, SOUS_TITRE_MAX) || null,
    message: _texte(x.message, MESSAGE_MAX) || null,
    cta_label: _texte(x.cta_label, CTA_MAX) || CTA_DEFAUT[type] || null,
    image_url: _texte(x.image_url) || null,
    image_source: _texte(x.image_source) || null,
    course_id: avecCours && x.course_id ? String(x.course_id) : null,
    occurrence: occurrence || null,
    offer_id: avecOffre && x.offer_id ? String(x.offer_id) : null,
  };
  // Défense : rien d'autre que la liste blanche ne sort d'ici.
  const propre = {};
  CHAMPS_CONTENU.forEach((k) => { propre[k] = corps[k] === undefined ? null : corps[k]; });
  return propre;
}

/**
 * Validation par type (fonction pure). Renvoie `{champ: message}` ; objet
 * vide = valide. `offers` sert à vérifier gratuité / payant ; `aujourdhui`
 * ("YYYY-MM-DD") refuse une date passée.
 */
export function validerInvitation(f, offers, aujourdhui) {
  const x = f || {};
  const e = {};
  const type = x.type;
  if (!TYPES_INVITATION.some((t) => t.id === type)) {
    e.type = "Choisis un type d'invitation.";
    return e;
  }
  const titre = String(x.title || '').trim();
  if (!titre) e.title = 'Donne un titre à ton invitation.';
  else if (titre.length > TITRE_MAX) e.title = `${TITRE_MAX} caractères au plus.`;
  if (String(x.subtitle || '').trim().length > SOUS_TITRE_MAX) e.subtitle = `${SOUS_TITRE_MAX} caractères au plus.`;
  if (String(x.message || '').length > MESSAGE_MAX) e.message = `${MESSAGE_MAX} caractères au plus.`;
  const cta = String(x.cta_label || '').trim();
  if (!cta) e.cta_label = 'Écris le texte du bouton.';
  else if (cta.length > CTA_MAX) e.cta_label = `${CTA_MAX} caractères au plus.`;

  const date = String(x.date || '').trim();
  const heure = String(x.heure || '').trim();
  const coursRequis = type === 'trial' || type === 'pass_duo';
  if (coursRequis) {
    if (!x.course_id) e.course_id = 'Choisis le cours.';
    if (!date) e.date = 'Choisis la date.';
    if (!heure) e.heure = "Indique l'heure.";
  } else if (date || heure) {
    // Événements : date et heure facultatives, mais jamais l'une sans l'autre.
    if (!date) e.date = 'Choisis la date (ou retire aussi l\'heure).';
    if (!heure) e.heure = "Indique l'heure (ou retire aussi la date).";
  }
  if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) e.date = 'Date illisible.';
  else if (date && /^\d{4}-\d{2}-\d{2}$/.test(String(aujourdhui || '')) && date < aujourdhui) e.date = 'Cette date est déjà passée.';
  if (heure && !heureDuCours(heure)) e.heure = 'Heure illisible.';

  const liste = Array.isArray(offers) ? offers : [];
  const offre = x.offer_id ? liste.find((o) => o && String(o.id) === String(x.offer_id)) : null;
  if (type === 'trial' || type === 'event_free') {
    if (!x.offer_id) e.offer_id = "Choisis l'offre gratuite.";
    else if (offre && !offreGratuite(offre)) e.offer_id = 'Cette offre est payante : choisis une offre gratuite.';
  } else if (type === 'event_paid') {
    if (!x.offer_id) e.offer_id = "Choisis l'offre payante de l'événement.";
    else if (offre && offreGratuite(offre)) e.offer_id = 'Cette offre est gratuite : choisis une offre payante.';
  }
  return e;
}

// ── Partage ────────────────────────────────────────────────────────────────

/** Le lien partagé : `share_url` du serveur tel quel (il porte déjà `?v=N`). */
export function lienPartage(dto) {
  return (dto && typeof dto.share_url === 'string') ? dto.share_url.trim() : '';
}

/** Le texte WhatsApp : message (sinon titre) + saut de ligne + lien courant. */
export function texteWhatsAppCampagne(dto) {
  const d = dto || {};
  const m = String(d.message || '').trim() || String(d.title || '').trim();
  return texteChaine(m, lienPartage(d));
}

/** L'invitation peut-elle être partagée ? (active, lien présent, pas un événement payant) */
export function partageable(dto) {
  return !!(dto && dto.status === 'active' && lienPartage(dto) && dto.type !== 'event_paid');
}

/** Message FR d'une erreur axios de la modale. */
export function messageErreur(err, contexte) {
  const rep = (err && err.response) || {};
  const s = rep.status || 0;
  if (s === 401 || s === 403) return TEXTE_RECONNEXION;
  if (s === 409 && contexte === 'activation') return TEXTE_FUSEAU_PALIERS;
  if (s === 404) return 'Cette invitation est introuvable.';
  if (s === 429) return 'Trop de tentatives. Réessaie dans un instant.';
  const d = rep.data && rep.data.detail;
  if ((s === 400 || s === 422) && typeof d === 'string' && d.trim()) return d;
  if (s === 400 || s === 422) return 'Certains champs ne sont pas acceptés. Vérifie-les puis réessaie.';
  return contexte === 'options'
    ? 'Impossible de charger tes cours et offres pour le moment.'
    : 'Enregistrement impossible pour le moment. Réessaie dans un instant.';
}

// ── Appels API (promesses axios brutes) ────────────────────────────────────

export function lireOptions(API) {
  return axios.get(`${racineApi(API)}/api/referral/campaigns/options`, { timeout: 15000 })
    .then((r) => {
      const d = (r && r.data) || {};
      return {
        courses: Array.isArray(d.courses) ? d.courses.filter((c) => c && c.id) : [],
        offers: Array.isArray(d.offers) ? d.offers.filter((o) => o && o.id) : [],
      };
    });
}

/** POST — création (toujours en brouillon). */
export function creerInvitation(API, corps) {
  const c = {};
  CHAMPS_CONTENU.forEach((k) => { c[k] = corps && corps[k] !== undefined ? corps[k] : null; });
  c.status = 'draft';
  return axios.post(`${racineApi(API)}/api/referral/campaigns`, c, { timeout: 20000 }).then((r) => (r && r.data) || {});
}

/** PUT — champs partiels (le type ne change plus après la création). */
export function modifierInvitation(API, id, champs) {
  const c = {};
  Object.keys(champs || {}).forEach((k) => {
    if (k === 'status' || (CHAMPS_CONTENU.indexOf(k) >= 0 && k !== 'type')) c[k] = champs[k];
  });
  return axios.put(`${racineApi(API)}/api/referral/campaigns/${encodeURIComponent(id)}`, c, { timeout: 20000 })
    .then((r) => (r && r.data) || {});
}

/** L'aperçu d'un brouillon (JWT requis → blob, jamais un <img src> direct). */
export function lireApercuBrouillon(API, id) {
  return axios.get(`${racineApi(API)}/api/share/invite-preview/${encodeURIComponent(id)}.jpg`,
    { responseType: 'blob', timeout: 20000 }).then((r) => r && r.data);
}

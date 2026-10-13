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
// V607 : les médias de la bibliothèque existante (aucun nouvel envoi de fichier).
export function lireMedias(API) {
  return axios.get(`${racineApi(API)}/api/prospection-medias`, { timeout: 15000, params: { limit: 50 } })
    .then((r) => ((r && r.data && Array.isArray(r.data.medias)) ? r.data.medias : []).filter((m) => m && m.url && m.statut !== 'archivee'));
}

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

/** V607 : le blocage « fuseau horaire des paliers » est levé (api/pricing.py lit
 *  l'heure suisse). Constante conservée pour les appelants anciens, plus affichée. */
export const TEXTE_FUSEAU_PALIERS = 'Les événements payants pourront être partagés dès la correction du fuseau horaire des paliers.';
export const LIEU_MAX = 160;
/** Message d'une session expirée / sans jeton (401 / 403). */
export const TEXTE_RECONNEXION = 'Reconnecte-toi pour créer une invitation';

/** Les seuls champs de contenu que le serveur reçoit (liste blanche). */
export const CHAMPS_CONTENU = [
  'type', 'title', 'subtitle', 'message', 'cta_label', 'image_url', 'image_source',
  'course_id', 'occurrence', 'offer_id',
  'lieu', 'video_url', 'audio_url', // V607
];

/** V607 — le nom FR de chaque champ, pour dire QUEL champ manque. */
export const LIBELLES_CHAMPS = {
  type: "le type d'invitation", offer_id: "l'offre", course_id: 'la séance', date: 'la date',
  heure: "l'heure", lieu: 'le lieu', title: 'le titre', subtitle: 'le sous-titre', message: 'le message',
  cta_label: 'le texte du bouton', video_url: 'la vidéo', audio_url: "l'audio",
};

/** V607 — « Il manque : la date, l'heure et le lieu. » (vide si rien ne manque). */
export function resumeErreurs(erreurs, champs) {
  const cles = Object.keys(erreurs || {}).filter((k) => !champs || champs.indexOf(k) >= 0);
  if (!cles.length) return '';
  const noms = cles.map((k) => LIBELLES_CHAMPS[k] || k);
  const liste = noms.length > 1 ? `${noms.slice(0, -1).join(', ')} et ${noms[noms.length - 1]}` : noms[0];
  return `À compléter : ${liste}.`;
}

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
  // V607 : prix progressif — `price` n'est qu'une sentinelle à 0 ; un palier ou un
  // prix actif positif dit « payant ».
  if (o.prix_actif && Number(o.prix_actif.prix) > 0) return false;
  if (o.has_progressive_pricing && ['price_early_bird', 'price_standard', 'price_last_minute']
    .some((k) => Number(o[k]) > 0)) return false;
  const p = Number(o.price);
  return !Number.isFinite(p) || p <= 0;
}

// INV-5 — CE QUE LE LIEN PROFOND PEUT RÉELLEMENT OUVRIR.
// Le serveur (`/options`) annote chaque offre (`openable` : `/?offre=<id>&reserver=1`
// l'ouvre-t-il ? + `course_ids` : ses cours rattachés) et chaque cours (`public` :
// visible et non archivé). Même règle qu'à l'activation (422 sinon) et que le front
// INV-2 (`verdictSeanceInvitation`) : une offre qui liste ses cours n'accepte
// qu'eux, une offre qui n'en liste aucun accepte tout cours public.
// Champ absent (réponse d'avant INV-5) = accepté : le serveur reste juge.

/** L'offre s'ouvre-t-elle par son lien ? */
export function offreOuvrable(o) {
  return !!o && o.openable !== false;
}

/** Essai / événement gratuit : la séance passe par la vitrine (INV-2). */
function _viaVitrine(type) {
  return type === 'trial' || type === 'event_free';
}

/**
 * Les cours proposables : pour trial / event_free, les cours PUBLICS, et — une
 * offre choisie qui liste ses cours — seulement ceux-là. Autres types : tous.
 */
export function coursPourInvitation(type, offre, courses) {
  const liste = (Array.isArray(courses) ? courses : []).filter((c) => c && c.id);
  if (!_viaVitrine(type)) return liste;
  const publics = liste.filter((c) => c.public !== false);
  const lies = offre && Array.isArray(offre.course_ids) ? offre.course_ids.map(String) : [];
  return lies.length ? publics.filter((c) => lies.indexOf(String(c.id)) >= 0) : publics;
}

/**
 * Les offres proposables pour un type : gratuites ET ouvrables par leur lien
 * (trial, event_free), payantes (event_paid), aucune (pass_duo). Un essai exige
 * une séance : avec `courses`, une offre d'essai sans aucun cours proposable
 * n'est pas proposée (aucune combinaison possible).
 */
export function offresPourType(type, offers, courses) {
  const liste = (Array.isArray(offers) ? offers : []).filter((o) => o && o.id);
  if (_viaVitrine(type)) {
    const ouvrables = liste.filter((o) => offreGratuite(o) && offreOuvrable(o));
    if (type !== 'trial' || !Array.isArray(courses)) return ouvrables;
    return ouvrables.filter((o) => coursPourInvitation(type, o, courses).length > 0);
  }
  // V607 : un BILLET d'événement — jamais un abonnement, une carte membre, une offre
  // privée ou masquée (annotation serveur `billet`). Filtre PROPRE à l'événement
  // payant : les autres types et le catalogue ne sont pas touchés.
  if (type === 'event_paid') return liste.filter((o) => !offreGratuite(o) && offreBillet(o));
  return [];
}

/** V607 — l'offre peut-elle servir de billet ? (`billet` du serveur ; absent = oui). */
export function offreBillet(o) {
  return !!o && o.billet !== false;
}

/** V607 — le lieu affiché : saisi > celui du cours > celui de l'offre. */
export function lieuInvitation(f, cours, offre) {
  const x = f || {};
  return String(x.lieu || (cours && cours.location) || (offre && offre.location) || '').trim();
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

/**
 * INV-5 — la date / l'heure tombent-elles sur une séance du cours ? (même règle
 * que le serveur `seance_du_cours` et le front INV-2). Rend `{date?, heure?}` :
 * un message par champ en défaut ; vide si c'est bon ou si on ne peut pas juger.
 */
export function ecartSeanceCours(cours, date, heure) {
  const e = {};
  if (!cours || !/^\d{4}-\d{2}-\d{2}$/.test(String(date || '')) || !heureDuCours(heure)) return e;
  const hc = heureDuCours(cours.time);
  if (hc && hc !== heureDuCours(heure)) e.heure = `Ce cours a lieu à ${hc}.`;
  const fixe = typeof cours.date === 'string' ? cours.date.trim().slice(0, 10) : '';
  if (fixe) {
    if (fixe !== date) e.date = "Ce cours n'a lieu qu'à sa date fixe.";
  } else {
    const w = Number(cours.weekday);
    if (Number.isInteger(w) && w >= 0 && w <= 6 && new Date(`${date}T12:00:00`).getDay() !== w) {
      e.date = "Ce cours n'a pas lieu ce jour-là.";
    } else if (Array.isArray(cours.dates_annulees) && cours.dates_annulees.some((x) => String(x).slice(0, 10) === date)) {
      e.date = "Ce cours n'a pas lieu ce jour-là (séance annulée)."; // V610
    }
  }
  return e;
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
    lieu: '', // V607 : événements seulement
    video_url: '',
    audio_url: '',
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
    // V607 : le lieu n'a de sens que pour un événement ; médias facultatifs.
    lieu: (type === 'event_free' || type === 'event_paid') ? (_texte(x.lieu, LIEU_MAX) || null) : null,
    video_url: _texte(x.video_url) || null,
    audio_url: _texte(x.audio_url) || null,
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
export function validerInvitation(f, offers, aujourdhui, courses) {
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
    else if (offre && !offreOuvrable(offre)) e.offer_id = "Cette offre n'est pas publiée : son lien ne s'ouvrirait pas.";
    // INV-5 : le cours doit être public et rattaché à l'offre ; la date, une vraie séance.
    if (x.course_id && Array.isArray(courses)) {
      const permis = coursPourInvitation(type, offre, courses);
      const c = permis.find((k) => String(k.id) === String(x.course_id));
      if (!c) e.course_id = "Ce cours n'est pas proposé avec cette offre : choisis un des cours de l'offre.";
      else {
        const ecart = ecartSeanceCours(c, date, heure);
        if (ecart.date && !e.date) e.date = ecart.date;
        if (ecart.heure && !e.heure) e.heure = ecart.heure;
      }
    }
  } else if (type === 'event_paid') {
    if (!x.offer_id) e.offer_id = "Choisis l'offre payante de l'événement.";
    else if (offre && offreGratuite(offre)) e.offer_id = 'Cette offre est gratuite : choisis une offre payante.';
    else if (offre && !offreBillet(offre)) e.offer_id = `Cette offre ne peut pas servir de billet (${offre.raison_non_billet || 'abonnement ou offre privée'}).`;
    else if (offre && offre.has_progressive_pricing && !offre.prix_actif) {
      e.offer_id = "Cette offre n'a pas de date d'événement : ses 3 paliers ne peuvent pas se calculer. Renseigne-la dans l'offre.";
    }
    // V607 : un billet se vend pour une date, une heure et un lieu précis.
    if (!date && !e.date) e.date = "Choisis la date de l'événement.";
    if (!heure && !e.heure) e.heure = "Indique l'heure de l'événement.";
    const cours = x.course_id && Array.isArray(courses) ? courses.find((c) => String(c.id) === String(x.course_id)) : null;
    if (!lieuInvitation(x, cours, offre)) e.lieu = "Indique le lieu de l'événement.";
    // Les paliers se calculent sur la date de l'événement DE L'OFFRE : la même, sinon
    // la carte et le paiement ne diraient pas le même prix.
    if (offre && offre.has_progressive_pricing && offre.countdown_date && date && !e.date) {
      if (date !== offre.countdown_date) e.date = `L'événement de cette offre a lieu le ${offre.countdown_date} : les paliers en dépendent.`;
      else if (offre.countdown_time && heure && heureDuCours(heure) !== heureDuCours(offre.countdown_time) && !e.heure) {
        e.heure = `L'événement de cette offre commence à ${heureDuCours(offre.countdown_time)}.`;
      }
    }
  }
  if (String(x.lieu || '').length > LIEU_MAX) e.lieu = `${LIEU_MAX} caractères au plus.`;
  return e;
}

// ── Partage ────────────────────────────────────────────────────────────────

/** Le lien partagé : `share_url` du serveur tel quel (il porte déjà `?v=N`). */
export function lienPartage(dto) {
  return (dto && typeof dto.share_url === 'string') ? dto.share_url.trim() : '';
}

function _maj(t) {
  const s = String(t || '').trim();
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
}

/**
 * V607 — LE MESSAGE WHATSAPP, PROPRE AU TYPE (court, humain ; lignes vides omises).
 * Emojis autorisés DANS le texte du message (jamais comme icônes d'interface).
 * Pass Duo : le texte d'avant (message, sinon titre, + lien), inchangé.
 */
export function texteWhatsAppCampagne(dto) {
  const d = dto || {};
  const lien = lienPartage(d);
  const prenom = String((d.inviter_display && d.inviter_display.prenom) || '').trim();
  const perso = String(d.message || '').trim();
  const quand = [d.date_label ? `📅 ${_maj(d.date_label)}` : '', d.time_label ? `⏰ ${d.time_label}` : '',
    d.lieu ? `📍 ${d.lieu}` : ''].filter(Boolean);
  if (d.type === 'trial') {
    return [
      prenom ? `🔥 ${prenom} t'invite à découvrir Afroboost !` : '🔥 Viens découvrir Afroboost !',
      '🎧 Cardio + danse afro + casques immersifs',
      perso, '', ...quand, '', '🎁 Ton premier cours est offert.', '',
      'Réserve ton essai ici :', lien, '', 'Et à ton tour, tu pourras inviter quelqu’un 💜',
    ].filter((l, i, a) => l !== '' || (a[i - 1] !== '' && i > 0)).join('\n').trim();
  }
  if (d.type === 'event_paid') {
    // V610 : accroche personnalisée par le SYSTÈME (prénom de l'invitant : coach ou
    // participant de la boule de neige) ; l'argument de l'événement vient du
    // sous-titre (repris dans chaque relais), jamais d'un média ni d'un prénom figé.
    const nom = String(d.title || d.offre_nom || 'un événement Afroboost').trim();
    const pitch = String(d.subtitle || '').trim();
    const pa = d.prix_actif || null;
    return [
      prenom ? `${prenom} t'invite à Afroboost 🔥🎧` : 'Afroboost t’invite 🔥🎧', '',
      `Viens vivre ${nom}${pitch ? ' :' : ' !'}`, pitch, perso, '', ...quand, '',
      pa ? `🎟️ Tarif actuel : ${libellePrix(pa.prix)}${pa.libelle && pa.palier !== 'regular' ? ` (${pa.libelle})` : ''}` : '',
      d.gratuit_membres ? '💜 Membre Afroboost ? Ton abonnement peut te donner un tarif spécial.' : '',   // V618M : jamais « 8 mois » en dur
      pa && pa.prochain ? 'Plus tu réserves tôt, moins c’est cher.' : '', '',
      'Réserve ta place 👇', lien,
    ].filter((l, i, a) => l !== '' || (a[i - 1] !== '' && i > 0)).join('\n').trim();
  }
  if (d.type === 'event_free') {
    const nom = String(d.title || d.offre_nom || 'un événement Afroboost').trim();
    return [
      prenom ? `🔥 ${prenom} t'invite : ${nom}` : `🔥 ${nom}`, perso, '', ...quand, '',
      '🎉 Entrée gratuite.', '', 'Inscris-toi ici :', lien,
    ].filter((l, i, a) => l !== '' || (a[i - 1] !== '' && i > 0)).join('\n').trim();
  }
  const m = perso || String(d.title || '').trim();
  return texteChaine(m, lien);
}

/** L'invitation peut-elle être partagée ? (active, lien présent) — V607 : l'événement
 *  payant aussi, depuis la correction du fuseau des paliers. */
export function partageable(dto) {
  return !!(dto && dto.status === 'active' && lienPartage(dto));
}

/**
 * V607 — L'APERÇU EN DIRECT (pur) : ce que la carte montrera, depuis le FORMULAIRE
 * (avant tout enregistrement). Jamais « 0 CHF » : « Offert » (essai), « Gratuit »
 * (événement gratuit), le prix ACTIF du serveur (événement payant), rien (Pass Duo).
 */
export function apercuDepuisFormulaire(f, offre, cours, inviteur) {
  const x = f || {};
  const type = x.type || '';
  let mention = null;
  if (type === 'trial') mention = 'Offert';
  else if (type === 'event_free') mention = 'Gratuit';
  else if (type === 'event_paid' && offre && offre.prix_actif) {
    const pa = offre.prix_actif;
    mention = `${libellePrix(pa.prix)}${pa.palier !== 'regular' && pa.libelle ? ` · ${pa.libelle}` : ''}`;
  }
  const date = /^\d{4}-\d{2}-\d{2}$/.test(String(x.date || '')) ? new Date(`${x.date}T12:00:00`) : null;
  const jours = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'];
  const mois = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];
  return {
    type,
    prenom: String((inviteur && inviteur.prenom) || '').trim(),
    titre: String(x.title || '').trim() || TITRE_DEFAUT[type] || '',
    sous_titre: String(x.subtitle || '').trim(),
    message: String(x.message || '').trim(),
    cta: String(x.cta_label || '').trim() || CTA_DEFAUT[type] || '',
    date_label: date ? `${jours[date.getDay()]} ${date.getDate()} ${mois[date.getMonth()]}` : '',
    time_label: heureDuCours(x.heure),
    lieu: (type === 'event_free' || type === 'event_paid' || type === 'trial' || type === 'pass_duo') ? lieuInvitation(x, cours, offre) : '',
    mention_prix: mention,
    paliers: type === 'event_paid' && offre && offre.prix_actif ? (offre.prix_actif.paliers || []) : [],
    image_url: String(x.image_url || '').trim(),
    video_url: String(x.video_url || '').trim(),
    audio_url: String(x.audio_url || '').trim(),
  };
}

/** Message FR d'une erreur axios de la modale. */
export function messageErreur(err, contexte) {
  const rep = (err && err.response) || {};
  const s = rep.status || 0;
  if (s === 401 || s === 403) return TEXTE_RECONNEXION;
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
        // V607 : qui invite (aperçu en direct, avant tout enregistrement).
        inviter_display: d.inviter_display && typeof d.inviter_display === 'object' ? d.inviter_display : null,
        default_image_url: d.default_image_url || null,
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

/** PUT — champs partiels. V607 : le TYPE part aussi tant que l'invitation est un
 *  brouillon (`avecType`) ; le serveur refuse (409) un changement après activation. */
export function modifierInvitation(API, id, champs, avecType) {
  const c = {};
  Object.keys(champs || {}).forEach((k) => {
    if (k === 'status' || (CHAMPS_CONTENU.indexOf(k) >= 0 && (k !== 'type' || avecType))) c[k] = champs[k];
  });
  return axios.put(`${racineApi(API)}/api/referral/campaigns/${encodeURIComponent(id)}`, c, { timeout: 20000 })
    .then((r) => (r && r.data) || {});
}

/** L'aperçu d'un brouillon (JWT requis → blob, jamais un <img src> direct). */
export function lireApercuBrouillon(API, id) {
  return axios.get(`${racineApi(API)}/api/share/invite-preview/${encodeURIComponent(id)}.jpg`,
    { responseType: 'blob', timeout: 20000 }).then((r) => r && r.data);
}

// ── V610o — PROGRAMME AMBASSADEUR : le message de l'Afroboosteur ────────────────
/** « AFROBOOST SILENT — ÉDITION SPÉCIALE » -> « Afroboost Silent — Édition Spéciale ». */
export function titreLisible(t) {
  const s = String(t || '').trim();
  if (!s || s !== s.toUpperCase()) return s;
  return s.toLowerCase().replace(/(^|[\s—\-'’(])(\p{L})/gu, (m, a, b) => a + b.toUpperCase());
}

/** « Chemin des Valangines 97, 2000 Neuchâtel » -> « Neuchâtel » (sinon le lieu). */
export function villeDuLieu(lieu) {
  const l = String(lieu || '').trim();
  const m = /\b\d{4}\s+([^,\d][^,]*)$/.exec(l);
  return m ? m[1].trim() : l;
}

/**
 * Le message d'un PARTICIPANT confirmé (événement payant) : membre (« Ma place est offerte »
 * = SA place, jamais celle de l'ami) ou billet payé. « 50 PLACES » vient de la configuration
 * du coach (un MESSAGE, jamais une capacité) ; « plus tu réserves tôt » seulement si un palier
 * de prix plus cher suit réellement. Champ absent -> ligne omise.
 */
export function texteAmbassadeur(dto, { nature, messagePlaces } = {}) {
  const d = dto || {};
  const lien = String(d.share_url || '');
  const complet = titreLisible(d.title || d.offre_nom || 'un événement Afroboost');
  const court = complet.split(/\s+—\s+/)[0] || complet;
  const heure = String(d.time_label || '').replace(/^(\d{1,2}):(\d{2})$/, '$1h$2');
  const quand = [d.date_label ? _maj(d.date_label) : '', heure].filter(Boolean).join(' · ');
  const ville = villeDuLieu(d.lieu);
  // V618L : plus de « 50 PLACES » par défaut — la ligne n'existe que si le serveur l'envoie
  // (événement à capacité RÉELLE). Un faux compteur ne part plus dans WhatsApp.
  const places = String(messagePlaces === undefined || messagePlaces === null ? '' : messagePlaces).trim();
  const pa = d.prix_actif || null;
  const plusTot = pa && pa.prochain ? 'Plus tu réserves tôt, moins c’est cher.' : '';
  const infos = [quand ? `📅 ${quand}` : '', ville ? `📍 ${ville}` : ''].filter(Boolean);
  const lignes = nature === 'membre'
    ? [`🔥 Je vais à ${court} !`, '',
      'Ma place est offerte grâce à mon abonnement Afroboost et j’aimerais que tu viennes vivre l’expérience avec moi 🎧💜', '',
      ...infos, '', places ? `🔥 ${places}` : '', '', plusTot, '', 'Viens vivre l’expérience avec moi 👇', lien]
    : ['🔥 Je deviens Afroboosteur !', '', `Je vais à ${complet} 🎧`, '', ...infos, '',
      places ? `🔥 ${places}` : '', '', plusTot, '', 'Viens vivre l’expérience avec moi 💜👇', lien];
  return lignes.filter((l, i, a) => l !== '' || (i > 0 && a[i - 1] !== '')).join('\n').trim();
}

/**
 * invitationSeance.js — INV-2 : la séance d'une invitation « Essai gratuit » /
 * « Événement gratuit » arrive DÉJÀ choisie.
 *
 * LE PARCOURS EXISTANT, INCHANGÉ (aucun nouveau tunnel) :
 *   1. /api/share/invite/<jeton> renvoie vers `/?offre=<id>&reserver=1`
 *      (+ INV-2 : `&course=<id>&occurrence=<AAAA-MM-JJTHH:MM>`) ;
 *   2. le lien profond d'App.js (V371/V449, P2-FIX2) ouvre le formulaire
 *      « Vos informations » de l'offre gratuite — ce formulaire n'a PAS de
 *      sélecteur de séance (V225 : `showSessions` reste faux pour 0 CHF) ;
 *   3. `POST /checkout/free` accorde le code AFR-, puis ESSAI-7 emmène la
 *      personne sur `/espace/AFR-XXXXXX` (`cibleRedirectionEssai`) ;
 *   4. c'est LÀ que la séance se choisit : liste `upcoming_courses` du serveur,
 *      état `selectedCourseIdx` de SubscriberSpace, bouton « Réserver ».
 *
 * INV-2 transporte donc la séance de 1 à 4 et la PRÉSÉLECTIONNE à l'étape 4
 * (l'index de la liste existante). Rien n'est réservé : la personne clique
 * elle-même sur « Réserver cette séance ». Aucun paiement ne s'ouvre.
 *
 * NOMS DE PARAMÈTRES : `course` / `occurrence`, ceux que /parrainage lit déjà
 * pour le même rôle (`lireContexteUrl`, utils/parrainage.js). Aucun nouveau nom.
 *
 * Ce module ne contient QUE des décisions pures : aucune requête, aucun DOM.
 */

export const MOTIF_COURS = /^[A-Za-z0-9_-]{1,64}$/;
export const MOTIF_OCCURRENCE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;

export const MESSAGE_SEANCE_INDISPONIBLE =
  'La séance de ton invitation n’est plus disponible. Choisis une autre séance ci-dessous.';
export const MESSAGE_SEANCE_INDISPONIBLE_FORMULAIRE =
  'La séance de ton invitation n’est plus disponible. Tu pourras choisir une autre séance juste après.';

/**
 * `{ offre, course, occurrence }` lus dans la query string, ou `null`.
 * Les DEUX paramètres de séance sont exigés et validés strictement ; un seul
 * hors motif et la séance est ignorée en entier (jamais à moitié).
 */
export function lireSeanceInvitation(search) {
  let q;
  try {
    q = new URLSearchParams(search != null ? search : (window.location.search || ''));
  } catch (e) {
    return null;
  }
  const course = String(q.get('course') || '').trim();
  const occurrence = String(q.get('occurrence') || '').trim();
  if (!MOTIF_COURS.test(course) || !MOTIF_OCCURRENCE.test(occurrence)) return null;
  const offre = String(q.get('offre') || '').trim();
  return { offre, course, occurrence };
}

/** « 18:30 », « 18h30 », « 9:05 » -> « 18:30 » / « 09:05 », sinon "". */
function heureNormalisee(t) {
  const m = /^\s*(\d{1,2})\s*[:hH.]\s*(\d{2})/.exec(String(t || ''));
  if (!m) return '';
  const h = parseInt(m[1], 10);
  const mn = parseInt(m[2], 10);
  if (h > 23 || mn > 59) return '';
  return `${String(h).padStart(2, '0')}:${String(mn).padStart(2, '0')}`;
}

/** L'occurrence (heure locale de la vitrine, convention LOT 1) en `Date`, ou null. */
export function dateOccurrence(occurrence) {
  if (!MOTIF_OCCURRENCE.test(String(occurrence || ''))) return null;
  const [j, h] = occurrence.split('T');
  const [a, mo, d] = j.split('-').map((x) => parseInt(x, 10));
  const [hh, mm] = h.split(':').map((x) => parseInt(x, 10));
  const dt = new Date(a, mo - 1, d, hh, mm, 0, 0);
  // Rejette les dates impossibles (31 février -> 3 mars).
  if (dt.getFullYear() !== a || dt.getMonth() !== mo - 1 || dt.getDate() !== d
    || dt.getHours() !== hh || dt.getMinutes() !== mm) return null;
  return dt;
}

/**
 * Le formulaire de la vitrine peut-il ANNONCER cette séance ?
 *
 * Mêmes règles que le serveur (`_v184_next_occurrences`) : cours visible et non
 * archivé, lié à l'offre (si l'offre liste ses cours), occurrence FUTURE, et
 * réellement proposée par le cours (date fixe + heure, ou jour de semaine JS
 * Dim=0..Sam=6 + heure). Le serveur reste l'autorité à l'étape suivante.
 *
 * @returns {null|{etat:'ok',cours,occurrence,date}|{etat:'indisponible'}}
 *          `null` = aucune séance d'invitation (parcours d'avant, à l'identique).
 */
export function verdictSeanceInvitation(seance, offre, cours, maintenant) {
  if (!seance || !offre) return null;
  // La séance appartient à l'offre du lien (`?offre=`), et à elle seule.
  if (!seance.offre || offre.id !== seance.offre) return null;
  const INDISPO = { etat: 'indisponible' };
  const liste = Array.isArray(cours) ? cours : [];
  const c = liste.find((x) => x && x.id === seance.course);
  if (!c || c.visible === false || c.archived === true) return INDISPO;
  const lies = Array.isArray(offre.linked_course_ids) ? offre.linked_course_ids : [];
  if (lies.length > 0 && lies.indexOf(c.id) === -1) return INDISPO;
  const dt = dateOccurrence(seance.occurrence);
  const now = maintenant instanceof Date ? maintenant : new Date();
  if (!dt || dt.getTime() <= now.getTime()) return INDISPO;
  const heure = seance.occurrence.slice(11, 16);
  if (heureNormalisee(c.time) !== heure) return INDISPO;
  const dateFixe = typeof c.date === 'string' ? c.date.trim().slice(0, 10) : '';
  if (dateFixe) {
    if (dateFixe !== seance.occurrence.slice(0, 10)) return INDISPO;
  } else {
    const wd = parseInt(c.weekday, 10);
    if (!(wd >= 0 && wd <= 6) || dt.getDay() !== wd) return INDISPO;
  }
  return { etat: 'ok', cours: c, occurrence: seance.occurrence, date: dt };
}

/** « jeudi 1 octobre · 18:30 » (fr), ou "". */
export function libelleSeance(occurrence) {
  const dt = dateOccurrence(occurrence);
  if (!dt) return '';
  let jour = '';
  try {
    jour = dt.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
  } catch (e) {
    jour = occurrence.slice(0, 10);
  }
  return `${jour} · ${occurrence.slice(11, 16)}`;
}

/**
 * La cible ESSAI-7 (`/espace/AFR-XXXXXX`) + la séance validée, ou la cible
 * telle quelle. `null` reste `null` : sans octroi prouvé, on ne va nulle part.
 */
export function cibleAvecSeance(cible, verdict) {
  if (!cible) return cible;
  if (!verdict || verdict.etat !== 'ok' || !verdict.cours) return cible;
  const course = String(verdict.cours.id || '');
  const occurrence = String(verdict.occurrence || '');
  if (!MOTIF_COURS.test(course) || !MOTIF_OCCURRENCE.test(occurrence)) return cible;
  const sep = cible.indexOf('?') === -1 ? '?' : '&';
  return `${cible}${sep}course=${encodeURIComponent(course)}&occurrence=${encodeURIComponent(occurrence)}`;
}

/**
 * Espace participant : l'index de la séance d'invitation dans la liste
 * `upcoming_courses` RÉELLEMENT affichée (celle du serveur, déjà filtrée par
 * ses règles : forfait, cours liés, fenêtre, places), ou -1.
 * Une activité « billet séparé » (`inclus_abonnement === false`) ne se réserve
 * pas ici : elle compte comme indisponible.
 */
export function indexSeanceInvitation(seance, occurrences) {
  if (!seance || !Array.isArray(occurrences)) return -1;
  for (let i = 0; i < occurrences.length; i += 1) {
    const o = occurrences[i];
    if (o && o.course_id === seance.course
      && String(o.datetime || '').slice(0, 16) === seance.occurrence
      && o.inclus_abonnement !== false) return i;
  }
  return -1;
}

/** INV-3 : la limite d'affichage historique de l'espace participant (V203f). */
export const SEANCES_VISIBLES_MAX = 12;

/**
 * INV-3 : la liste RÉELLEMENT affichée par l'espace participant — la SEULE
 * source de l'affichage ET de la présélection (`indexSeanceInvitation`).
 *
 * Les 12 premières séances, comme avant ; plus la séance de l'invitation si
 * elle est au-delà (le serveur l'ajoute jusqu'à J+30, en fin de liste triée) :
 * elle n'est jamais coupée. Sans invitation, ou si elle est absente / billet
 * séparé : exactement les 12 premières.
 */
export function seancesVisibles(courses, seanceInvitee) {
  const liste = Array.isArray(courses) ? courses : [];
  const tete = liste.slice(0, SEANCES_VISIBLES_MAX);
  if (!seanceInvitee || liste.length <= SEANCES_VISIBLES_MAX) return tete;
  const i = indexSeanceInvitation(seanceInvitee, liste);
  if (i < SEANCES_VISIBLES_MAX) return tete;
  return [...tete, liste[i]];
}

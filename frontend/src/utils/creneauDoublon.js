// =============================================================================
// V663 — COURS, SÉANCE, OFFRE : TROIS CHOSES, ET ON NE LES CONFOND PLUS
// =============================================================================
//
// LE BUG MESURÉ (11/11/2026, base de production). Dans `OfferWizard`, le bouton
// « Ajouter un horaire » créait un cours NOMMÉ COMME L'OFFRE :
//
//     name: (form.name && form.name.trim()) || 'Nouveau cours',   // V251
//
// Créer l'offre « Cours à l'unité » puis y ajouter un horaire fabriquait donc
// un COURS appelé « Cours à l'unité ». Résultat en base : la même séance
// physique existe DEUX FOIS, et chacune reçoit des réservations.
//
//   mercredi 18:45, Valangines 97 — « Afroboost Silent – Session Cardio » : 71 résa
//   mercredi 18:45, Valangines 97 — « Cours à l'unité »                   : 13 résa
//   dimanche 18:30, Valangines 97 — « Afroboost Silent – Sunday Vibes »   : 55 résa
//   dimanche 18:30, Valangines 97 — « Cours à l'unité »                   : 12 résa
//
// Une offre est une CONDITION D'ACCÈS (unité, pack, abonnement, carte). Elle ne
// décrit aucune activité et ne doit jamais donner son nom à une séance.
// Le lien existe déjà et il est correct : `offers.linked_course_ids`. Une offre
// peut viser plusieurs cours, et un cours peut être visé par plusieurs offres —
// mesuré : « Session Cardio » est relié à 11 offres, et n'apparaît qu'une fois.
//
// CE QUE CE MODULE FAIT, ET SURTOUT CE QU'IL NE FAIT PAS.
// Il AVERTIT quand un créneau identique existe déjà, pour que le coach le
// RATTACHE au lieu d'en créer un second. Il ne fusionne RIEN, ne supprime RIEN,
// ne réécrit RIEN : deux cours réellement différents à la même heure doivent
// rester possibles (« Afroboost Silent » et un autre cours le même mercredi à
// 18:45 = DEUX créneaux). La décision reste au coach, toujours.

/** Comparaison tolérante : accents, casse, ponctuation et espaces ignorés. */
export function normaliser(valeur) {
  return String(valeur == null ? '' : valeur)
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')   // accents
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

/** « 18:45 », « 18h45 », « 8:45 » -> minutes depuis minuit, ou null. */
export function minutesDeLHeure(valeur) {
  const m = /^\s*(\d{1,2})\s*[:hH.]\s*(\d{1,2})\s*$/.exec(String(valeur || ''));
  if (!m) return null;
  const h = parseInt(m[1], 10);
  const mn = parseInt(m[2], 10);
  if (!(h >= 0 && h <= 23) || !(mn >= 0 && mn <= 59)) return null;
  return h * 60 + mn;
}

// V664b — « CHEM. » ET « CHEMIN » SONT LA MÊME RUE.
// Trouvé par le garde-fou de la migration : les deux fiches du mercredi 18:45
// portaient la même adresse écrite autrement (« Chem. des Valangines 97 » et
// « Chemin des Valangines 97 »). Sans cela, un simple point d'abréviation
// suffisait à contourner la règle qu'elle est censée appliquer.
// Liste VOLONTAIREMENT COURTE, limitée aux types de voie : ni noms propres, ni
// numéros. L'élargir rapprocherait des adresses réellement différentes.
const TYPES_DE_VOIE = {
  chem: 'chemin', av: 'avenue', bd: 'boulevard', blvd: 'boulevard',
  rte: 'route', pl: 'place', r: 'rue', imp: 'impasse',
  sq: 'square', all: 'allee', qu: 'quai', fbg: 'faubourg',
};

/** Le lieu d'un cours, quel que soit le champ qui le porte. */
export function lieuDe(cours) {
  const c = cours || {};
  return normaliser(c.locationName || c.location || '')
    .split(' ')
    .map((mot) => TYPES_DE_VOIE[mot] || mot)
    .join(' ');
}

/**
 * MÊME OCCURRENCE PHYSIQUE ? Trois conditions, toutes nécessaires :
 * le même moment (date exacte, ou le même jour de semaine pour un récurrent),
 * la même heure, et le même lieu.
 *
 * LE LIEU EST OBLIGATOIRE DANS LA COMPARAISON. Sans lui, deux cours tenus à la
 * même heure dans deux salles différentes seraient confondus — c'est
 * précisément ce que la règle interdit. Si l'un des deux lieux est inconnu, on
 * ne conclut PAS : on préfère ne rien signaler plutôt que signaler à faux.
 *
 * Un cours PONCTUEL (avec `date`) et un cours RÉCURRENT ne sont jamais
 * rapprochés : leurs identités sont de nature différente.
 */
export function memeCreneau(a, b) {
  if (!a || !b) return false;
  const ha = minutesDeLHeure(a.time);
  const hb = minutesDeLHeure(b.time);
  if (ha == null || hb == null || ha !== hb) return false;

  const la = lieuDe(a);
  const lb = lieuDe(b);
  if (!la || !lb) return false;        // lieu inconnu : on ne conclut pas
  if (la !== lb) return false;

  const da = String(a.date || '').trim();
  const dbb = String(b.date || '').trim();
  if (da || dbb) return Boolean(da) && Boolean(dbb) && da === dbb;

  // Récurrents : le jour de semaine doit correspondre, et être connu.
  const ja = a.weekday;
  const jb = b.weekday;
  if (ja === null || ja === undefined || ja === '' ) return false;
  if (jb === null || jb === undefined || jb === '') return false;
  return parseInt(ja, 10) === parseInt(jb, 10);
}

/**
 * Le cours existant qui occupe DÉJÀ ce créneau, ou null.
 *
 * On ignore les cours archivés : ils ne sont plus proposés, les rattacher
 * n'aurait pas de sens. On ignore aussi celui qu'on est en train de modifier
 * (`exclureId`), sinon un cours se signalerait lui-même.
 */
export function creneauDejaPris(cours, candidat, exclureId) {
  if (!Array.isArray(cours) || !candidat) return null;
  for (let i = 0; i < cours.length; i += 1) {
    const c = cours[i];
    if (!c || c.archived === true) continue;
    if (exclureId && c.id === exclureId) continue;
    if (memeCreneau(c, candidat)) return c;
  }
  return null;
}

/**
 * LE NOM D'UNE SÉANCE NE VIENT JAMAIS D'UNE OFFRE.
 *
 * `nomsDOffres` est la liste des noms commerciaux connus. Si le nom proposé en
 * est un, on le refuse et on rend le libellé provisoire : le coach nommera
 * l'ACTIVITÉ (« Afroboost Silent », « Afroboost Live », …).
 *
 * Aucune exception codée pour un nom particulier : la règle vaut pour « Cours à
 * l'unité » comme pour toute offre présente ou future.
 */
export const NOM_PROVISOIRE = 'Séance à nommer';

export function nomDeSeance(nomPropose, nomsDOffres) {
  const n = String(nomPropose == null ? '' : nomPropose).trim();
  if (!n) return NOM_PROVISOIRE;
  const liste = Array.isArray(nomsDOffres) ? nomsDOffres : [];
  const cible = normaliser(n);
  for (let i = 0; i < liste.length; i += 1) {
    if (cible && normaliser(liste[i]) === cible) return NOM_PROVISOIRE;
  }
  return n;
}

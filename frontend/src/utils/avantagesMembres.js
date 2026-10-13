/**
 * V618M — AVANTAGES MEMBRES PAR OFFRE + URGENCE / PLACES (éditeur d'un événement payant).
 *
 * Le coach choisit, offre par offre (identifiant RÉEL, jamais un titre) : aucun avantage,
 * gratuit, réduction % ou prix membre fixe. Le serveur revalide tout et calcule seul le prix ;
 * ces fonctions ne servent qu'à l'écran (formulaire, différences, aperçu).
 *
 * Urgence : le TEXTE marketing (« 50 PLACES », « ÉDITION LIMITÉE »…) et la CAPACITÉ réelle sont
 * deux réglages séparés : le texte ne limite jamais rien.
 */
export const TYPES_AVANTAGE = [
  { valeur: 'aucun', libelle: 'Aucun avantage' },
  { valeur: 'gratuit', libelle: 'Gratuit' },
  { valeur: 'reduction', libelle: 'Réduction %' },
  { valeur: 'prix_fixe', libelle: 'Prix fixe' },
];
export const TEXTE_URGENCE_MAX = 40;

/** Le formulaire de départ, depuis ce que le serveur a rendu (`evenement.avantages` / `urgence`). */
export function formAvantages(evt) {
  const a = (evt && evt.avantages) || null;
  const u = (evt && evt.urgence) || {};
  return {
    avantages: a ? (a.regles || []).map((r) => ({ offer_id: r.offer_id, nom: r.nom, type: r.type,
      valeur: r.valeur == null ? '' : String(r.valeur), active: r.active !== false })) : null,
    urgence: { texte: u.texte || '', visible: !!u.visible, capacite_limitee: !!u.capacite_limitee,
      capacite_max: u.capacite_max != null ? String(u.capacite_max) : '' },
  };
}

/** Ce qui part au serveur pour une ligne (« aucun » est omis : c'est l'absence d'avantage). */
export function regleEnvoyee(r) {
  if (!r || !r.offer_id || r.type === 'aucun') return null;
  if (r.type === 'gratuit') return { offer_id: r.offer_id, type: 'gratuit' };
  const v = Number(String(r.valeur).replace(',', '.'));
  return { offer_id: r.offer_id, type: r.type, valeur: r.type === 'reduction' ? Math.round(v) : Math.round(v * 100) / 100 };
}

function cleRegles(liste) {
  return JSON.stringify((liste || []).map(regleEnvoyee).filter(Boolean)
    .map((r) => ({ offer_id: r.offer_id, type: r.type === 'reduction' && r.valeur === 100 ? 'gratuit' : r.type,
      valeur: r.type === 'gratuit' || (r.type === 'reduction' && r.valeur === 100) ? null : r.valeur }))
    .sort((x, y) => (x.offer_id < y.offer_id ? -1 : 1)));
}

/** Le contrôle client (le serveur revalide). Rend un message ou ''. */
export function erreurAvantages(form) {
  for (const r of (form && form.avantages) || []) {
    const v = Number(String(r.valeur).replace(',', '.'));
    if (r.type === 'reduction' && !(Number.isFinite(v) && v >= 1 && v <= 100)) return `${r.nom} : la réduction doit être entre 1 et 100 %.`;
    if (r.type === 'prix_fixe' && !(String(r.valeur).trim() !== '' && Number.isFinite(v) && v >= 0 && v <= 10000)) return `${r.nom} : indique un prix membre en CHF.`;
  }
  const u = (form && form.urgence) || {};
  if (String(u.texte || '').length > TEXTE_URGENCE_MAX) return `Le texte d'urgence fait ${TEXTE_URGENCE_MAX} caractères au plus.`;
  if (u.capacite_limitee) {
    const c = Number(u.capacite_max);
    if (!Number.isInteger(c) || c < 1 || c > 10000) return 'Indique une capacité maximum (nombre de places, de 1 à 10000).';
  }
  return '';
}

/** Les changements à envoyer (`avantages_membres`, `urgence`), comparés à l'état serveur. */
export function changementsAvantages(form, evt) {
  const c = {};
  if (!form || !evt) return c;
  if (evt.avantages && form.avantages && cleRegles(form.avantages) !== cleRegles((evt.avantages.regles || []).map((r) => Object.assign({}, r, { valeur: r.valeur == null ? '' : r.valeur })))) {
    c.avantages_membres = form.avantages.map(regleEnvoyee).filter(Boolean);
  }
  const u0 = (evt.urgence) || {};
  const u = form.urgence || {};
  const du = {};
  if (String(u.texte || '').trim() !== String(u0.texte || '')) du.texte = String(u.texte || '').trim();
  if (!!u.visible !== !!u0.visible) du.visible = !!u.visible;
  const max0 = u0.capacite_max != null ? Number(u0.capacite_max) : null;
  if (!!u.capacite_limitee !== !!u0.capacite_limitee || (u.capacite_limitee && Number(u.capacite_max) !== max0)) {
    du.capacite_limitee = !!u.capacite_limitee;
    if (u.capacite_limitee) du.capacite_max = Number(u.capacite_max);
  }
  if (Object.keys(du).length) c.urgence = du;
  return c;
}

/** « 24 CHF au lieu de 30 CHF » : le résumé d'une règle, pour un prix public donné (aperçu). */
export function prixMembreApercu(regle, prixPublic) {
  const pub = Number(prixPublic);
  if (!regle || !Number.isFinite(pub)) return null;
  const v = Number(String(regle.valeur).replace(',', '.'));
  let m = pub;
  if (regle.type === 'gratuit') m = 0;
  else if (regle.type === 'reduction' && Number.isFinite(v)) m = pub * (100 - Math.round(v)) / 100;
  else if (regle.type === 'prix_fixe' && Number.isFinite(v)) m = v;
  return Math.max(0, Math.min(pub, Math.round(m * 100) / 100));
}

/** « 24 CHF » / « 12.50 CHF ». */
export function chf(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return '';
  return `${Number.isInteger(v) ? v : v.toFixed(2)} CHF`;
}

/**
 * contactsAffichage.js — CONTACTS V2, temps 2
 *
 * Tri, libellés et drapeaux. Aucune règle métier ici : les quatre dimensions
 * sont dérivées par le serveur au temps 1, cet écran ne fait que les montrer.
 *
 * Chaque état porte du TEXTE, jamais une couleur seule : « Participant » se lit,
 * une pastille violette se devine.
 */

export const TRIS = [
  { id: 'nom_az', libelle: 'Nom A-Z' },
  { id: 'nom_za', libelle: 'Nom Z-A' },
  { id: 'recent', libelle: 'Plus récent' },
  { id: 'ancien', libelle: 'Plus ancien' },
  { id: 'abonnes', libelle: 'Abonnés d’abord' },
];

const LIBELLES_TYPE = {
  participant: 'Participant', prospect: 'Prospect',
  partner: 'Partenaire', other: 'Autre',
};
const LIBELLES_STATUT = {
  actif: 'Abonné actif', ancien: 'Ancien abonné', non_abonne: 'Non abonné',
};
const LIBELLES_ZONE = {
  suisse: 'Suisse', afrique: 'Afrique', europe: 'Europe',
  autre: 'Autre', inconnue: 'Zone inconnue',
};
const DRAPEAUX = {
  CH: '🇨🇭', FR: '🇫🇷', BE: '🇧🇪', DE: '🇩🇪', IT: '🇮🇹', ES: '🇪🇸', GB: '🇬🇧',
  PT: '🇵🇹', NL: '🇳🇱', AT: '🇦🇹', LU: '🇱🇺', MC: '🇲🇨',
  CM: '🇨🇲', SN: '🇸🇳', CI: '🇨🇮', ML: '🇲🇱', BF: '🇧🇫', NE: '🇳🇪', TG: '🇹🇬',
  BJ: '🇧🇯', GH: '🇬🇭', NG: '🇳🇬', CF: '🇨🇫', GA: '🇬🇦', CG: '🇨🇬', CD: '🇨🇩',
  MA: '🇲🇦', DZ: '🇩🇿', TN: '🇹🇳', GM: '🇬🇲', GN: '🇬🇳', TD: '🇹🇩', KE: '🇰🇪', ZA: '🇿🇦',
};
const NOMS_PAYS = {
  CH: 'Suisse', FR: 'France', BE: 'Belgique', DE: 'Allemagne', IT: 'Italie',
  ES: 'Espagne', GB: 'Royaume-Uni', PT: 'Portugal', NL: 'Pays-Bas', AT: 'Autriche',
  LU: 'Luxembourg', MC: 'Monaco', CM: 'Cameroun', SN: 'Sénégal', CI: "Côte d'Ivoire",
  ML: 'Mali', BF: 'Burkina Faso', NE: 'Niger', TG: 'Togo', BJ: 'Bénin', GH: 'Ghana',
  NG: 'Nigeria', CF: 'Centrafrique', GA: 'Gabon', CG: 'Congo', CD: 'RD Congo',
  MA: 'Maroc', DZ: 'Algérie', TN: 'Tunisie', GM: 'Gambie', GN: 'Guinée',
  TD: 'Tchad', KE: 'Kenya', ZA: 'Afrique du Sud',
};

/** « Non classé » est un état affiché, pas un vide. */
export const libelleType = (c) => LIBELLES_TYPE[(c || {}).contact_type] || 'Non classé';
export const libelleStatut = (c) => LIBELLES_STATUT[(c || {}).statut_abonnement] || 'Non abonné';
export const libelleZone = (c) => {
  const p = (c || {}).pays;
  if (p && NOMS_PAYS[p]) return NOMS_PAYS[p];
  return LIBELLES_ZONE[(c || {}).zone] || 'Zone inconnue';
};
export const drapeau = (c) => DRAPEAUX[(c || {}).pays] || '';
export const nomPays = (code) => NOMS_PAYS[code] || code;

/** Les pays réellement présents, pour ne proposer que des filtres qui servent. */
export function paysPresents(contacts) {
  const vus = new Map();
  (contacts || []).forEach((c) => {
    if (c && c.pays) vus.set(c.pays, (vus.get(c.pays) || 0) + 1);
  });
  return [...vus.entries()]
    .sort((a, b) => b[1] - a[1] || nomPays(a[0]).localeCompare(nomPays(b[0])))
    .map(([code, n]) => ({ code, nom: nomPays(code), drapeau: DRAPEAUX[code] || '', n }));
}

export function trierContacts(contacts, tri) {
  const l = [...(contacts || [])];
  const nom = (c) => (c.name || '').toLocaleLowerCase('fr');
  const date = (c) => String(c.created_at || '');
  switch (tri) {
    case 'nom_za': return l.sort((a, b) => nom(b).localeCompare(nom(a), 'fr'));
    case 'recent': return l.sort((a, b) => date(b).localeCompare(date(a)));
    case 'ancien': return l.sort((a, b) => date(a).localeCompare(date(b)));
    case 'abonnes': {
      const rang = (c) => (c.statut_abonnement === 'actif' ? 0
        : c.statut_abonnement === 'ancien' ? 1 : 2);
      return l.sort((a, b) => rang(a) - rang(b) || nom(a).localeCompare(nom(b), 'fr'));
    }
    default: return l.sort((a, b) => nom(a).localeCompare(nom(b), 'fr'));
  }
}

/**
 * contactType.js — ESSAI-5a-2
 *
 * La valeur STOCKÉE est en anglais, le libellé AFFICHÉ en français. Les deux
 * ne doivent jamais se confondre : renommer un libellé casserait la donnée.
 *
 * « Absent » n'est pas « Autre ». Un contact non classé n'a pas été jugé ;
 * un contact « Autre » l'a été. Seul `participant` ouvre l'invitation à
 * témoigner — rien n'est déduit d'une adresse, d'un code ou d'une source.
 */
export const TYPES_CONTACT = [
  { valeur: 'participant', libelle: 'Participant' },
  { valeur: 'prospect', libelle: 'Prospect' },
  { valeur: 'partner', libelle: 'Partenaire' },
  { valeur: 'other', libelle: 'Autre' },
];

export const libelleType = (valeur) => {
  const t = TYPES_CONTACT.find((x) => x.valeur === valeur);
  return t ? t.libelle : '';
};

export const estParticipant = (contact) =>
  String((contact || {}).contact_type || '') === 'participant';

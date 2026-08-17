/**
 * contactsFiltres.js — CONTACTS V2, temps 1
 *
 * Quatre dimensions qui ne se confondent pas :
 *   RELATION           contact_type, posé à la main
 *   STATUT COMMERCIAL  actif / ancien / non abonné, dérivé
 *   ZONE               pays déduit de l'indicatif, dérivé
 *   CANAL              e-mail / WhatsApp / téléphone disponibles
 *
 * Et une cinquième, qu'on ne confond surtout pas avec le canal :
 *   CONSENTEMENT       autorisé / refusé / inconnu, PAR canal
 *
 * Avoir un numéro n'est pas avoir le droit d'écrire. Un filtre « WhatsApp »
 * dit que le canal existe, jamais qu'une campagne est permise.
 *
 * Le serveur dérive, cet écran ne fait que filtrer ce qu'il reçoit.
 */

export const TYPES = [
  { valeur: 'participant', libelle: 'Participant' },
  { valeur: 'prospect', libelle: 'Prospect' },
  { valeur: 'partner', libelle: 'Partenaire' },
  { valeur: 'other', libelle: 'Autre' },
  { valeur: '__non_classe__', libelle: 'Non classé' },
];

export const STATUTS = [
  { valeur: 'actif', libelle: 'Abonné actif' },
  { valeur: 'ancien', libelle: 'Ancien abonné' },
  { valeur: 'non_abonne', libelle: 'Non abonné' },
];

export const ZONES = [
  { valeur: 'suisse', libelle: 'Suisse' },
  { valeur: 'afrique', libelle: 'Afrique' },
  { valeur: 'europe', libelle: 'Europe' },
  { valeur: 'autre', libelle: 'Autre' },
  { valeur: 'inconnue', libelle: 'Inconnue' },
];

export const CANAUX = [
  { valeur: 'email', libelle: 'Email' },
  { valeur: 'whatsapp', libelle: 'WhatsApp' },
  { valeur: 'telephone', libelle: 'Téléphone' },
];

export const CONSENTEMENTS = [
  { valeur: 'autorise', libelle: 'Autorisé' },
  { valeur: 'refuse', libelle: 'Non autorisé' },
  { valeur: 'inconnu', libelle: 'Inconnu' },
];

export const FILTRES_VIDES = {
  types: [], statuts: [], zones: [], pays: [], canaux: [],
  consentEmail: [], consentWhatsapp: [],
};

export const nombreFiltresActifs = (f) =>
  Object.keys(FILTRES_VIDES).reduce((n, k) => n + ((f && f[k]) ? f[k].length : 0), 0);

const sansAccents = (t) => (t || '')
  .toString().normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

/** Une case cochée = un OU dans sa dimension ; les dimensions se cumulent en ET. */
export function filtrerContacts(contacts, filtres, recherche) {
  const f = { ...FILTRES_VIDES, ...(filtres || {}) };
  const q = sansAccents(recherche);
  const chiffres = (recherche || '').replace(/\D/g, '');

  return (contacts || []).filter((c) => {
    if (q || chiffres) {
      const surNom = sansAccents(c.name).includes(q);
      const surMail = sansAccents(c.email).includes(q);
      // On tape « 079… » pour trouver « +4179… » : le 0 national doit donc
      // aussi être essayé sans lui, sinon la recherche par numéro ne trouve
      // presque rien — la base est majoritairement en E.164.
      const numContact = String(c.whatsapp || c.phone || '').replace(/\D/g, '');
      const sansZero = chiffres.replace(/^0+/, '');
      const surNum = numContact !== '' && (
        (chiffres.length >= 3 && numContact.includes(chiffres))
        || (sansZero.length >= 3 && numContact.includes(sansZero))
      );
      if (!(surNom || surMail || surNum)) return false;
    }

    if (f.types.length) {
      const t = c.contact_type || '__non_classe__';
      if (!f.types.includes(t)) return false;
    }
    if (f.statuts.length && !f.statuts.includes(c.statut_abonnement || 'non_abonne')) return false;
    if (f.zones.length && !f.zones.includes(c.zone || 'inconnue')) return false;
    // Le pays PRÉCISE, il ne remplace pas la zone : cocher « Cameroun » sans
    // cocher « Afrique » doit fonctionner.
    if (f.pays.length && !f.pays.includes(c.pays || '')) return false;

    // Canal : la case demande « ce canal existe », pas « tous les cochés ».
    if (f.canaux.length) {
      const dispo = c.canaux || {};
      if (!f.canaux.some((k) => dispo[k])) return false;
    }

    const cons = c.consentement || {};
    if (f.consentEmail.length && !f.consentEmail.includes(cons.email || 'inconnu')) return false;
    if (f.consentWhatsapp.length && !f.consentWhatsapp.includes(cons.whatsapp || 'inconnu')) return false;

    return true;
  });
}

/** Les cinq vues rapides du haut de page. Rien d'autre n'y monte. */
export const VUES_RAPIDES = [
  { id: 'tous', libelle: 'Tous', filtres: FILTRES_VIDES },
  { id: 'participants', libelle: 'Participants', filtres: { ...FILTRES_VIDES, types: ['participant'] } },
  { id: 'abonnes', libelle: 'Abonnés', filtres: { ...FILTRES_VIDES, statuts: ['actif'] } },
  { id: 'prospects', libelle: 'Prospects', filtres: { ...FILTRES_VIDES, types: ['prospect'] } },
  { id: 'non_classes', libelle: 'Non classés', filtres: { ...FILTRES_VIDES, types: ['__non_classe__'] } },
];

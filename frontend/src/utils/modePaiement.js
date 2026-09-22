// V535 — Choix du mode de paiement d'une offre « saison en 2 fois » qui le permet.
//
// Tout vient de l'OFFRE (liste blanche publique) : `billing_mode`, `price`,
// `full_payment_available`, `installment_interval_months`. Aucun montant, aucun
// intervalle n'est écrit ici ; le serveur revalide le mode et RECALCULE le montant.
// Fonctions pures, testables sans React.
export const MODE_INTEGRAL = 'full';
export const MODE_2X = '2x';
const ECHEANCES = 2;
const INTERVALLE_HISTORIQUE = 4;

const nombre = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : null; };
export const arrondiCHF = (v) => Math.round((nombre(v) || 0) * 100) / 100;
export const chf = (v) => `${arrondiCHF(v).toFixed(2).replace('.', ',')} CHF`;

/** Vrai si l'acheteur DOIT choisir entre « en une fois » et « en 2 fois ». */
export function offreAvecChoixPaiement(offre) {
  return !!offre && offre.billing_mode === 'saison_2x' && offre.full_payment_available === true;
}

/** Mois entre les deux échéances : la valeur de l'offre (1..12) sinon l'historique (4). */
export function intervalleMois(offre) {
  const n = parseInt(offre && offre.installment_interval_months, 10);
  return Number.isInteger(n) && n >= 1 && n <= 12 ? n : INTERVALLE_HISTORIQUE;
}

/**
 * Les deux options affichables. `prixEcheance` = prix de l'offre (une échéance),
 * `total` = prix × 2. `null` si l'offre ne laisse pas le choix.
 */
export function optionsPaiement(offre, prixAffiche) {
  if (!offreAvecChoixPaiement(offre)) return null;
  const echeance = arrondiCHF(prixAffiche != null ? prixAffiche : offre.price);
  if (!(echeance > 0)) return null;
  const total = arrondiCHF(echeance * ECHEANCES);
  const mois = intervalleMois(offre);
  return {
    total,
    echeance,
    echeances: ECHEANCES,
    intervalleMois: mois,
    integral: { mode: MODE_INTEGRAL, titre: 'Paiement intégral', detail: chf(total) },
    deuxFois: {
      mode: MODE_2X,
      titre: 'Paiement en 2 fois',
      detail: `${chf(echeance)} aujourd’hui puis ${chf(echeance)} dans ${mois} mois`,
    },
  };
}

// V535 — helper pur du choix de mode de paiement.
import { offreAvecChoixPaiement, optionsPaiement, intervalleMois, chf } from '../modePaiement';

const M8 = { id: 'ba530ae4', name: 'Membres — 8 mois', price: 199.99, billing_mode: 'saison_2x', full_payment_available: true, installment_interval_months: 1 };
const AUTRE = { id: 'x', price: 299, billing_mode: 'saison_2x' };

describe('V535 modePaiement (pur)', () => {
  test('seule une offre saison_2x AVEC full_payment_available laisse le choix', () => {
    expect(offreAvecChoixPaiement(M8)).toBe(true);
    expect(offreAvecChoixPaiement(AUTRE)).toBe(false);
    expect(offreAvecChoixPaiement({ ...M8, full_payment_available: 'true' })).toBe(false);
    expect(offreAvecChoixPaiement({ ...M8, billing_mode: 'unique' })).toBe(false);
    expect(offreAvecChoixPaiement(null)).toBe(false);
  });
  test('options : intégral 399,98 ; 2 fois 199,99 aujourd’hui puis 199,99 dans 1 mois ; total identique', () => {
    const o = optionsPaiement(M8);
    expect(o.total).toBe(399.98);
    expect(o.echeance).toBe(199.99);
    expect(o.integral).toEqual({ mode: 'full', titre: 'Paiement intégral', detail: '399,98 CHF' });
    expect(o.deuxFois.mode).toBe('2x');
    expect(o.deuxFois.detail).toBe('199,99 CHF aujourd’hui puis 199,99 CHF dans 1 mois');
  });
  test('intervalle : valeur de l’offre (1..12) sinon 4 (règle historique)', () => {
    expect(intervalleMois(M8)).toBe(1);
    expect(intervalleMois(AUTRE)).toBe(4);
    expect(intervalleMois({ installment_interval_months: 0 })).toBe(4);
    expect(intervalleMois({ installment_interval_months: 13 })).toBe(4);
  });
  test('prix affiché (palier actif) prioritaire sur price ; offre sans choix → null', () => {
    expect(optionsPaiement(M8, 150).total).toBe(300);
    expect(optionsPaiement(AUTRE)).toBeNull();
    expect(chf(199.99)).toBe('199,99 CHF');
  });
});

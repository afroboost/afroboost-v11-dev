/**
 * BilanAssociation — l'écran affiche EXACTEMENT le bilan du serveur, un appel par
 * changement de filtre, aucun sondage ; les exports passent par fetch + jeton
 * (blob), jamais par un lien direct ; aucune donnée personnelle n'est rendue.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import axios from 'axios';

jest.mock('axios', () => ({ get: jest.fn() }));
jest.mock('recharts', () => {
  const Stub = ({ children }) => <div>{children}</div>;
  return { ResponsiveContainer: Stub, LineChart: Stub, BarChart: Stub, Line: () => null, Bar: () => null,
    XAxis: () => null, YAxis: () => null, Tooltip: () => null, CartesianGrid: () => null, Legend: () => null };
});

const BilanAssociation = require('../BilanAssociation').default;
const { parametresBilan, nomFichier, moisCourantISO, telechargerExport } = require('../BilanAssociation');

const ASSOC = {
  periode: { debut: '2026-08-01', fin_exclue: '2026-09-01', libelle: 'Août 2026' },
  perimetre: { libelle: 'Ensemble Afroboost / Association', cours: 'tous', note: '' },
  activite: { seances: 12, reservations: 25, participants_uniques: 15, nouveaux: 7, recurrents: 8, moyenne_par_seance: 2.08,
    mercredi: { reservations: 11, seances: 5, moyenne: 2.2, participants: 6 }, dimanche: { reservations: 8, seances: 5, moyenne: 1.6, participants: 6 }, autres_jours: 6 },
  presence: { confirmee: 6, absente: 0, inconnue: 19, reservations: 25, couverture_pct: 24.0, libelle: '6 présence(s) vérifiée(s) sur 25 réservations — couverture 24,0 %' },
  essais: { accordes: 9, reserves: 0, presence_confirmee: 0, presence_inconnue: 0, couverture_pct: null, conversions_confirmees: 0, conversions_probables: 0 },
  fidelisation: { '1': 7, '2_5': 2, '6_10': 2, plus_10: 4 },
  abonnements: { actifs: 32, nouveaux: 19, expires: 3, pulse_actifs: 6, pulse_vendus: 3, cartes_actives: 6, cartes_vendues: 0, renouvellements_confirmes: 0, renouvellements_probables: 3, note_probables: 'x' },
  finances: { ca_prouve: 575, stripe: 575, manuel: 0, achats_payes: 10, gratuits: 8, panier_moyen: 57.5, acheteurs_uniques: 10,
    par_moyen: { stripe_indetermine: { libelle: 'Stripe — moyen non déterminé', nombre: 9, montant: 425 } },
    hors_ca: { declare_non_prouve_montant: 0, declare_non_prouve_nombre: 0, pending_nombre: 77, pending_montant: 3640, inconnus: 1, note: '' },
    remboursements: 'Remboursements non disponibles historiquement' },
  qualite: { presence: 'partiel', valeur_financiere: 'partiel', montants: 'partiel', moyen_paiement: 'partiel', renouvellements: 'partiel', conversion: 'inconnu', phrases: ['Présence : 6 présence(s) vérifiée(s) sur 25 réservations — couverture 24,0 %.'] },
  comparaison: { periode_precedente: { debut: '2026-07-01', fin_exclue: '2026-08-01', libelle: 'Juillet 2026' }, indicateurs: {
    reservations: { actuel: 25, precedent: 18, variation_pct: 38.9, libelle: '+38,9 %', libelle_indicateur: 'Réservations' },
    essais: { actuel: 9, precedent: 0, variation_pct: null, libelle: 'nouveau', libelle_indicateur: 'Essais accordés' },
    ca_prouve: { actuel: 575, precedent: 256, variation_pct: 124.6, libelle: '+124,6 %', libelle_indicateur: 'CA prouvé (CHF)' } } },
  evolution_annuelle: { annee: 2026, mois: [...Array(12)].map((_, i) => ({ mois: ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sept', 'Oct', 'Nov', 'Déc'][i], numero: i + 1, participants: i === 7 ? 15 : 0, reservations: i === 7 ? 25 : 0, seances: i === 7 ? 12 : 0, essais: 0, ca_prouve: i === 7 ? 575 : 0, futur: i > 8 })) },
  resume_executif: 'En août 2026, Afroboost a organisé 12 séance(s) réunissant 15 participant(s) unique(s) pour 25 réservation(s).',
  genere_le: '2026-09-15 09:14',
};
const KPI = { association: ASSOC, cours_disponibles: [{ id: 'c1', name: 'Silent', reservations: 20 }] };

function monter(props) {
  const div = document.createElement('div');
  document.body.appendChild(div);
  const root = createRoot(div);
  act(() => { root.render(<BilanAssociation {...props} />); });
  return { div, root };
}

beforeEach(() => { axios.get.mockReset(); jest.useRealTimers(); });

describe('helpers', () => {
  test('parametresBilan : vue=association, mois ou année, coach et cours seulement si choisis', () => {
    expect(parametresBilan({ mode: 'mois', mois: '2026-08' })).toEqual({ vue: 'association', periode: 'mois', granularite: 'mois', mois: '2026-08' });
    expect(parametresBilan({ mode: 'annee', mois: '2026-08', coachId: 'c@x', courseId: 'k' })).toEqual({ vue: 'association', periode: 'annee', granularite: 'mois', mois: '2026-08', coach_id: 'c@x', course_id: 'k' });
  });
  test('nomFichier et moisCourantISO', () => {
    expect(nomFichier('pdf', { debut: '2026-08-01' })).toBe('bilan-afroboost-2026-08.pdf');
    expect(moisCourantISO(new Date(2026, 8, 15))).toBe('2026-09');
  });
  test('telechargerExport : fetch AVEC axios (jeton par intercepteur), blob, sans vue/granularite, nom de fichier', async () => {
    axios.get.mockResolvedValue({ data: new Blob(['x']) });
    global.URL.createObjectURL = jest.fn(() => 'blob:u'); global.URL.revokeObjectURL = jest.fn();
    const ouvrir = jest.fn();
    await telechargerExport('csv', { vue: 'association', periode: 'mois', granularite: 'mois', mois: '2026-08' }, { debut: '2026-08-01' }, ouvrir);
    expect(axios.get).toHaveBeenCalledWith(expect.stringMatching(/\/analytics\/export$/), { params: { periode: 'mois', mois: '2026-08', format: 'csv' }, responseType: 'blob' });
    expect(ouvrir).toHaveBeenCalledWith('blob:u', 'bilan-afroboost-2026-08.csv');
  });
});

describe('BilanAssociation', () => {
  test('un appel au montage (vue=association, mois courant), aucun sondage', async () => {
    jest.useFakeTimers();
    axios.get.mockResolvedValue({ data: KPI });
    monter({});
    await act(async () => {});
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(axios.get.mock.calls[0][1].params).toMatchObject({ vue: 'association', periode: 'mois' });
    act(() => { jest.advanceTimersByTime(10 * 60 * 1000); });
    expect(axios.get).toHaveBeenCalledTimes(1);
  });

  test('affiche le bilan du serveur : résumé, cartes, hors CA à part, comparaison, évolution, qualité, pied', async () => {
    axios.get.mockResolvedValue({ data: KPI });
    const { div } = monter({});
    await act(async () => {});
    const t = (id) => div.querySelector(`[data-testid="${id}"]`).textContent;
    expect(t('bilan-titre')).toBe('Bilan Août 2026');
    expect(t('bilan-perimetre')).toContain('Ensemble Afroboost / Association');
    expect(t('bilan-resume')).toContain('12 séance(s)');
    expect(t('bilan-seances')).toContain('12');
    expect(t('bilan-reservations')).toContain('25');
    expect(t('bilan-uniques')).toContain('15');
    expect(t('bilan-uniques')).toContain('7 nouveaux · 8 récurrents');
    expect(t('bilan-ca')).toContain('575,00 CHF');
    expect(t('bilan-presence')).toContain('6 présence(s) vérifiée(s) sur 25');
    expect(t('bilan-hors-ca')).toContain('jamais additionnés au CA prouvé');
    expect(t('bilan-hors-ca')).toContain('77 · 3 640,00 CHF déclarés');
    expect(t('bilan-pulse')).toContain('6');
    expect(t('bilan-cartes')).toContain('6');
    expect(t('bilan-conversions')).toContain('KPI principal');
    expect(t('comparaison-reservations')).toContain('18 → 25');
    expect(t('comparaison-reservations')).toContain('+38,9 %');
    expect(t('comparaison-essais')).toContain('nouveau');
    expect(t('evolution-8')).toContain('575,00 CHF');
    expect(div.querySelectorAll('[data-testid^="evolution-"]').length).toBe(12);
    expect(t('evolution-10')).toContain('(à venir)');
    expect(t('evolution-8')).not.toContain('(à venir)');
    expect(t('bilan-qualite')).toContain('couverture 24,0 %');
    expect(t('bilan-finances')).toContain('Stripe — moyen non déterminé');
    expect(div.textContent).toContain('Les données personnelles des participants ne sont pas incluses');
    expect(div.textContent).not.toMatch(/@/);
  });

  test('changer de mois / passer en année : un appel par changement, avec mois=YYYY-MM', async () => {
    axios.get.mockResolvedValue({ data: KPI });
    const { div } = monter({});
    await act(async () => {});
    const input = div.querySelector('[data-testid="filtre-mois"]');
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, '2026-07');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(axios.get).toHaveBeenCalledTimes(2);
    expect(axios.get.mock.calls[1][1].params).toMatchObject({ periode: 'mois', mois: '2026-07' });
    await act(async () => { div.querySelector('[data-testid="mode-annee"]').click(); });
    expect(axios.get).toHaveBeenCalledTimes(3);
    expect(axios.get.mock.calls[2][1].params).toMatchObject({ periode: 'annee', mois: '2026-07' });
  });

  test('filtre cours : note de périmètre affichée quand le serveur la renvoie', async () => {
    axios.get.mockResolvedValue({ data: { ...KPI, association: { ...ASSOC, perimetre: { libelle: 'Coach Afroboost', cours: 'c1', note: 'Le filtre cours ne s\'applique qu\'à l\'activité et à la présence ; essais, abonnements et finances restent globaux (période / coach).' } } } });
    const { div } = monter({});
    await act(async () => {});
    expect(div.querySelector('[data-testid="bilan-perimetre"]').textContent).toContain('Coach Afroboost');
    expect(div.querySelector('[data-testid="bilan-note-cours"]').textContent).toContain('restent globaux');
  });

  test('exports : trois boutons, clic = un GET /analytics/export en blob (pas de lien direct)', async () => {
    axios.get.mockResolvedValue({ data: KPI });
    global.URL.createObjectURL = jest.fn(() => 'blob:u'); global.URL.revokeObjectURL = jest.fn();
    const { div } = monter({});
    await act(async () => {});
    axios.get.mockResolvedValue({ data: new Blob(['%PDF']) });
    const clic = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    await act(async () => { div.querySelector('[data-testid="export-pdf"]').click(); });
    expect(axios.get).toHaveBeenLastCalledWith(expect.stringMatching(/\/analytics\/export$/), { params: { periode: 'mois', mois: expect.any(String), format: 'pdf' }, responseType: 'blob' });
    expect(clic).toHaveBeenCalled();
    expect(div.querySelector('a[href^="/api/analytics/export"]')).toBeNull();
    clic.mockRestore();
  });

  test('401 -> accès refusé, rien d\'affiché', async () => {
    axios.get.mockRejectedValue({ response: { status: 401 } });
    const { div } = monter({});
    await act(async () => {});
    expect(div.querySelector('[role="alert"]').textContent).toMatch(/Accès refusé/);
    expect(div.querySelector('[data-testid="bilan-titre"]')).toBeNull();
  });
});

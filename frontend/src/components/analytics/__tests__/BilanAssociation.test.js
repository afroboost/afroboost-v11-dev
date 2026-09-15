/**
 * BilanAssociation — l'écran affiche EXACTEMENT le bilan du serveur, un appel par
 * changement de filtre, aucun sondage ; les exports passent par fetch + jeton
 * (blob), jamais par un lien direct ; aucune donnée personnelle n'est rendue.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import axios from 'axios';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock('recharts', () => {
  const Stub = ({ children }) => <div>{children}</div>;
  return { ResponsiveContainer: Stub, LineChart: Stub, BarChart: Stub, Line: () => null, Bar: () => null,
    XAxis: () => null, YAxis: () => null, Tooltip: () => null, CartesianGrid: () => null, Legend: () => null };
});

const BilanAssociation = require('../BilanAssociation').default;
const { parametresBilan, nomFichier, moisCourantISO, telechargerExport, telechargerExportOfficiel } = require('../BilanAssociation');
const appelsCockpit = () => axios.get.mock.calls.filter((c) => /\/analytics\/cockpit$/.test(c[0]));
const appelsArchives = () => axios.get.mock.calls.filter((c) => /\/analytics\/clotures$/.test(c[0]));
/** Le serveur factice : cockpit -> KPI, clotures -> liste, clotures/<id> -> snapshot. */
function serveur({ kpi = KPI, clotures = [], snapshot = null } = {}) {
  axios.get.mockImplementation((url) => {
    if (/\/analytics\/clotures$/.test(url)) return Promise.resolve({ data: { clotures, perimetre: 'tous' } });
    if (/\/analytics\/clotures\/[^/]+$/.test(url)) return Promise.resolve({ data: snapshot });
    if (/\/export$/.test(url)) return Promise.resolve({ data: new Blob(['x']) });
    return Promise.resolve({ data: kpi });
  });
}

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
const KPI = { association: ASSOC, cours_disponibles: [{ id: 'c1', name: 'Silent', reservations: 20 }], cloture: { existante: null, cloturable: false, raison: 'Le mois n\'est pas terminé : la clôture n\'est possible qu\'après sa fin.', super_admin: true } };
const META = { id: 'snap-1', cle: '2026-08:tous', annee: 2026, mois: 8, periode: { debut: '2026-08-01', fin_exclue: '2026-09-01', libelle: 'Août 2026' }, perimetre: { libelle: 'Ensemble Afroboost / Association', coach_id: null }, statut: 'officiel', version: 1, created_at: '2026-09-15T12:00:00', created_by: 'admin@exemple.invalid', hash: 'abcdef123456789' };
const SNAPSHOT = { cloture: META, bilan: { ...ASSOC, finances: { ...ASSOC.finances, ca_prouve: 575 }, cloture: { officiel: true, version: 1, hash: META.hash, libelle: 'BILAN OFFICIEL — clôturé le 2026-09-15 12:00 (v1) — empreinte abcdef123456' } } };
const KPI_CLOTURABLE = { ...KPI, cloture: { existante: null, cloturable: true, raison: '', super_admin: true } };
const KPI_CLOTURE = { ...KPI, association: { ...ASSOC, finances: { ...ASSOC.finances, ca_prouve: 605 } }, cloture: { existante: META, cloturable: false, raison: 'Ce mois est déjà clôturé pour ce périmètre ; une clôture n\'est jamais écrasée.', super_admin: true } };

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
  test('un appel principal au montage (vue=association, mois courant) + un pour les archives, aucun sondage', async () => {
    jest.useFakeTimers();
    serveur();
    monter({});
    await act(async () => {});
    expect(appelsCockpit().length).toBe(1);
    expect(appelsArchives().length).toBe(1);
    expect(appelsCockpit()[0][1].params).toMatchObject({ vue: 'association', periode: 'mois' });
    act(() => { jest.advanceTimersByTime(10 * 60 * 1000); });
    expect(axios.get).toHaveBeenCalledTimes(2);
  });

  test('affiche le bilan du serveur : résumé, cartes, hors CA à part, comparaison, évolution, qualité, pied', async () => {
    serveur();
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

  test('changer de mois / passer en année : un appel cockpit par changement, avec mois=YYYY-MM', async () => {
    serveur();
    const { div } = monter({});
    await act(async () => {});
    const input = div.querySelector('[data-testid="filtre-mois"]');
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, '2026-07');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(appelsCockpit().length).toBe(2);
    expect(appelsCockpit()[1][1].params).toMatchObject({ periode: 'mois', mois: '2026-07' });
    await act(async () => { div.querySelector('[data-testid="mode-annee"]').click(); });
    expect(appelsCockpit().length).toBe(3);
    expect(appelsCockpit()[2][1].params).toMatchObject({ periode: 'annee', mois: '2026-07' });
    expect(appelsArchives().length).toBe(1);   // les archives ne sont pas rechargées à chaque filtre
  });

  test('filtre cours : note de périmètre affichée quand le serveur la renvoie', async () => {
    serveur({ kpi: { ...KPI, association: { ...ASSOC, perimetre: { libelle: 'Coach Afroboost', cours: 'c1', note: 'Le filtre cours ne s\'applique qu\'à l\'activité et à la présence ; essais, abonnements et finances restent globaux (période / coach).' } } } });
    const { div } = monter({});
    await act(async () => {});
    expect(div.querySelector('[data-testid="bilan-perimetre"]').textContent).toContain('Coach Afroboost');
    expect(div.querySelector('[data-testid="bilan-note-cours"]').textContent).toContain('restent globaux');
  });

  test('exports : trois boutons, clic = un GET /analytics/export en blob (pas de lien direct)', async () => {
    serveur();
    global.URL.createObjectURL = jest.fn(() => 'blob:u'); global.URL.revokeObjectURL = jest.fn();
    const { div } = monter({});
    await act(async () => {});
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

describe('BilanAssociation — phase 4 clôture', () => {
  test('mois non clôturable : ni bouton, ni bannière ; raison affichée ; statut « données actuelles »', async () => {
    serveur();
    const { div } = monter({});
    await act(async () => {});
    expect(div.querySelector('[data-testid="cloturer"]')).toBeNull();
    expect(div.querySelector('[data-testid="bilan-cloture"]')).toBeNull();
    expect(div.querySelector('[data-testid="cloture-raison"]').textContent).toContain("n'est pas terminé");
    expect(div.querySelector('[data-testid="bilan-statut"]').textContent).toMatch(/Données actuelles \/ dynamiques/);
    expect(div.querySelector('[data-testid="bilan-archives"]').textContent).toContain('Aucun bilan clôturé');
  });

  test('mois clôturable : bouton -> confirmation (texte exact, Annuler / Clôturer) -> POST une fois -> rechargement', async () => {
    serveur({ kpi: KPI_CLOTURABLE });
    axios.post.mockResolvedValue({ data: { cloture: META, message: 'Bilan Août 2026 clôturé.' } });
    const { div } = monter({});
    await act(async () => {});
    expect(axios.post).not.toHaveBeenCalled();
    await act(async () => { div.querySelector('[data-testid="cloturer"]').click(); });
    expect(axios.post).not.toHaveBeenCalled();   // pas de clôture en un clic
    const conf = div.querySelector('[data-testid="confirmation-cloture"]');
    expect(conf.textContent).toContain("Vous allez figer définitivement le bilan d'août 2026. Les données de ce rapport ne changeront plus même si les données historiques sont corrigées.");
    await act(async () => { div.querySelector('[data-testid="annuler-cloture"]').click(); });
    expect(div.querySelector('[data-testid="confirmation-cloture"]')).toBeNull();
    expect(axios.post).not.toHaveBeenCalled();
    await act(async () => { div.querySelector('[data-testid="cloturer"]').click(); });
    serveur({ kpi: KPI_CLOTURE, clotures: [META] });   // après clôture, le serveur répond « clôturé »
    await act(async () => { div.querySelector('[data-testid="confirmer-cloture"]').click(); });
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/analytics\/cloture$/), null, { params: { mois: expect.any(String) } });
    expect(div.querySelector('[data-testid="bilan-message"]').textContent).toContain('clôturé');
    expect(div.querySelector('[data-testid="bilan-cloture"]').textContent).toContain('Bilan clôturé');
    expect(div.querySelector('[data-testid="cloturer"]')).toBeNull();
    expect(div.querySelector('[data-testid="archive-2026-08:tous"]').textContent).toContain('Officiel · v1');
  });

  test('mois clôturé : bannière (date, version, auteur), officiel ≠ dynamique, exports officiels depuis le snapshot', async () => {
    serveur({ kpi: KPI_CLOTURE, clotures: [META], snapshot: SNAPSHOT });
    global.URL.createObjectURL = jest.fn(() => 'blob:u'); global.URL.revokeObjectURL = jest.fn();
    const { div } = monter({});
    await act(async () => {});
    const t = (id) => div.querySelector(`[data-testid="${id}"]`).textContent;
    expect(t('bilan-cloture')).toContain('Clôturé le 2026-09-15 12:00');
    expect(t('bilan-cloture')).toContain('version 1');
    expect(t('bilan-cloture')).toContain('admin@exemple.invalid');
    // vue par défaut = données ACTUELLES (605), clairement étiquetées
    expect(t('bilan-statut')).toMatch(/Données actuelles/);
    expect(t('bilan-ca')).toContain('605,00 CHF');
    expect(div.querySelector('[data-testid="export-pdf"]')).not.toBeNull();
    // bascule vers l'OFFICIEL : lecture du snapshot, 575 figé, étiquette officielle
    await act(async () => { div.querySelector('[data-testid="voir-officiel"]').click(); });
    expect(axios.get).toHaveBeenCalledWith(expect.stringMatching(/\/analytics\/clotures\/snap-1$/));
    expect(t('bilan-statut')).toMatch(/Officiel \/ figé/);
    expect(t('bilan-titre')).toContain('officiel');
    expect(t('bilan-ca')).toContain('575,00 CHF');
    expect(t('bilan-officiel-meta')).toContain('BILAN OFFICIEL');
    const clic = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    await act(async () => { div.querySelector('[data-testid="export-officiel-pdf"]').click(); });
    expect(axios.get).toHaveBeenLastCalledWith(expect.stringMatching(/\/analytics\/clotures\/snap-1\/export$/), { params: { format: 'pdf' }, responseType: 'blob' });
    clic.mockRestore();
    // retour aux données actuelles
    await act(async () => { div.querySelector('[data-testid="voir-actuel"]').click(); });
    expect(t('bilan-statut')).toMatch(/Données actuelles/);
    expect(t('bilan-ca')).toContain('605,00 CHF');
  });

  test('archives : Voir / PDF / XLSX / CSV depuis le snapshot ; nom de fichier officiel', async () => {
    serveur({ kpi: KPI_CLOTURE, clotures: [META], snapshot: SNAPSHOT });
    global.URL.createObjectURL = jest.fn(() => 'blob:u'); global.URL.revokeObjectURL = jest.fn();
    const ouvrir = jest.fn();
    await telechargerExportOfficiel('snap-1', 'xlsx', META, ouvrir);
    expect(ouvrir).toHaveBeenCalledWith('blob:u', 'bilan-officiel-afroboost-2026-08-v1.xlsx');
    const { div } = monter({});
    await act(async () => {});
    const clic = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    await act(async () => { div.querySelector('[data-testid="archive-csv-2026-08:tous"]').click(); });
    expect(axios.get).toHaveBeenLastCalledWith(expect.stringMatching(/\/analytics\/clotures\/snap-1\/export$/), { params: { format: 'csv' }, responseType: 'blob' });
    clic.mockRestore();
  });

  test('période personnalisée / année : le serveur dit non clôturable -> aucun bouton actif, explication affichée', async () => {
    serveur({ kpi: { ...KPI, cloture: { existante: null, cloturable: false, raison: 'Une période personnalisée ne peut pas être clôturée. Sélectionnez un mois complet.', super_admin: true } } });
    const { div } = monter({});
    await act(async () => {});
    expect(div.querySelector('[data-testid="cloturer"]')).toBeNull();
    expect(div.querySelector('[data-testid="confirmer-cloture"]')).toBeNull();
    expect(div.querySelector('[data-testid="cloture-raison"]').textContent).toContain('Sélectionnez un mois complet');
    // le mode Année de cet écran envoie periode=annee : jamais de bouton non plus
    await act(async () => { div.querySelector('[data-testid="mode-annee"]').click(); });
    expect(div.querySelector('[data-testid="cloturer"]')).toBeNull();
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('coach (super_admin false) : jamais de bouton Clôturer, même sur un mois terminé', async () => {
    serveur({ kpi: { ...KPI, cloture: { existante: null, cloturable: false, raison: '', super_admin: false } } });
    const { div } = monter({});
    await act(async () => {});
    expect(div.querySelector('[data-testid="cloturer"]')).toBeNull();
    expect(div.querySelector('[data-testid="cloture-raison"]')).toBeNull();
  });
});

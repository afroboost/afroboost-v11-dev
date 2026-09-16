/**
 * V532 — admin Codes promo : « Abonnement actuel » d'abord, « Historique » replié,
 * « À vérifier » pour un doublon technique. Aucune fiche n'est supprimée ni masquée.
 * Le classement vient du serveur (`code.v532`), avec repli local si absent.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import PromoCodesTab from '../PromoCodesTab';

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn() }));
// CRA `resetMocks: true` efface les implémentations entre les tests : on les repose à chaque fois.
beforeEach(() => { require('axios').get.mockImplementation(() => Promise.resolve({ data: {} })); });
jest.mock('../index', () => ({ CreditsGate: ({ children }) => <>{children}</> }));
jest.mock('../../SvgIcon', () => ({ name }) => <i data-icon={name} />);

const t = (k) => k;
const base = {
  hasCreditsFor: () => true, servicePrices: {}, coachCredits: 99, setTab: () => {},
  codesSearch: '', setCodesSearch: () => {}, newCode: { courses: [], assignedEmails: [] }, setNewCode: () => {},
  isBatchMode: false, setIsBatchMode: () => {}, batchLoading: false,
  showManualContactForm: false, setShowManualContactForm: () => {}, manualContact: {}, setManualContact: () => {},
  uniqueCustomers: [], selectedBeneficiaries: [], toggleBeneficiarySelection: () => {},
  courses: [], offers: [], toggleCourseSelection: () => {}, removeAllowedArticle: () => {},
  addCode: () => {}, deleteCode: () => {}, toggleCode: () => {}, duplicateCode: () => {}, editCode: () => {},
  addManualContact: () => {}, handleImportCSV: () => {}, exportPromoCodesCSV: () => {}, manualSanitize: () => {},
  editingCode: null, t,
};
const fiche = (id, code, email, used, max, exp, active, v532) => ({ id, code, assignedEmail: email, used, maxUses: max, expiresAt: exp, active, v532 });
const AM = 'amanda@example.com';

function monter(codes) {
  const div = document.createElement('div'); document.body.appendChild(div);
  const root = createRoot(div);
  act(() => { root.render(<PromoCodesTab {...base} discountCodes={codes} />); });
  return { div, q: (sel) => div.querySelector(sel), qa: (sel) => div.querySelectorAll(sel), unmount: () => act(() => root.unmount()) };
}

test('E. Amanda : AmandaBoost-26 = Abonnement actuel, BASSBOOSTX-09 (2 fiches) = Historique', () => {
  const m = monter([
    fiche('8f4fb225', 'BASSBOOSTX-09', AM, 31, 47, '2026-05-05', false, { classement: 'historique', motif: 'inactif', utilise: 31, total: 47, restant: 16 }),
    fiche('d5737a11', 'BASSBOOSTX-09', AM, 8, 10, '2026-08-17', true, { classement: 'historique', motif: 'expire', utilise: 8, total: 10, restant: 2 }),
    fiche('086e316f', 'AmandaBoost-26', AM, 8, 9, '2026-10-05', true, { classement: 'actuel', motif: 'unique', utilise: 8, total: 9, restant: 1 }),
  ]);
  expect(m.q(`[data-testid="v532-personne-${AM}"]`)).toBeTruthy();
  expect(m.qa('[data-testid^="v532-actuel-"]').length).toBe(1);
  expect(m.q('[data-testid="v532-actuel-086e316f"]')).toBeTruthy();
  expect(m.q('[data-testid="v532-resume-086e316f"]').textContent).toMatch(/ACTIF · 8 \/ 9 utilisées · 1 restante · Expire le/);
  const hist = m.q(`[data-testid="v532-historique-${AM}"]`);
  expect(hist.tagName).toBe('DETAILS');
  expect(hist.querySelector('summary').textContent).toMatch(/Historique \(2\)/);
  expect(m.q('[data-testid="v532-historique-8f4fb225"]')).toBeTruthy();
  expect(m.q('[data-testid="v532-historique-d5737a11"]')).toBeTruthy();
  // aucune fiche perdue : les 3 lignes (avec leurs boutons) sont rendues
  expect(m.qa('[data-testid^="promo-code-"]').length).toBe(3);
  expect(m.qa('[data-testid^="delete-code-"]').length).toBe(3);
  m.unmount();
});

test('A. 1 actif + 2 historiques -> 1 bloc actuel, 2 dans l\'historique', () => {
  const m = monter([
    fiche('h1', 'P-1', 'x@example.com', 10, 10, '2026-03-01', true, { classement: 'historique', motif: 'expire' }),
    fiche('h2', 'P-2', 'x@example.com', 5, 5, '2026-06-01', true, { classement: 'historique', motif: 'epuise' }),
    fiche('ok', 'P-3', 'x@example.com', 2, 8, '2026-12-31', true, { classement: 'actuel', motif: 'unique', utilise: 2, total: 8, restant: 6 }),
  ]);
  expect(m.qa('[data-testid^="v532-actuel-"]').length).toBe(1);
  expect(m.q('[data-testid="v532-historique-x@example.com"] summary').textContent).toMatch(/Historique \(2\)/);
  expect(m.q('[data-testid="v532-plusieurs-x@example.com"]')).toBeNull();
  m.unmount();
});

test('B. 2 abonnements actifs valides -> les deux visibles, « Plusieurs droits actifs », aucun masqué', () => {
  const m = monter([
    fiche('b1', 'B-1', 'y@example.com', 1, 8, '2026-12-31', true, { classement: 'actuel', utilise: 1, total: 8, restant: 7 }),
    fiche('b2', 'B-2', 'y@example.com', 0, 4, '2026-11-30', true, { classement: 'actuel', utilise: 0, total: 4, restant: 4 }),
  ]);
  expect(m.qa('[data-testid^="v532-actuel-"]').length).toBe(2);
  expect(m.q('[data-testid="v532-plusieurs-y@example.com"]')).toBeTruthy();
  expect(m.q('[data-testid="v532-historique-y@example.com"]')).toBeNull();
  m.unmount();
});

test('C. ancien expiré + nouveau actif -> le nouveau est l\'actuel (repli local sans v532)', () => {
  const m = monter([
    fiche('c0', 'OLD', 'z@example.com', 8, 8, '2026-01-01', true, undefined),
    fiche('c1', 'NEW', 'z@example.com', 0, 8, '2026-12-01', true, undefined),
  ]);
  expect(m.q('[data-testid="v532-actuel-c1"]')).toBeTruthy();
  expect(m.q('[data-testid="v532-actuel-c0"]')).toBeNull();
  expect(m.q('[data-testid="v532-historique-c0"]')).toBeTruthy();
  m.unmount();
});

test('D. vrai doublon technique -> « À vérifier », groupé, les deux fiches rendues, aucune supprimée', () => {
  const m = monter([
    fiche('d1', 'DOUBLE', 'w@example.com', 9, 45, '2026-12-31', true, { classement: 'a_verifier', motif: 'plusieurs_docs_code' }),
    fiche('d2', 'DOUBLE', 'w@example.com', 6, 12, '2026-12-31', true, { classement: 'a_verifier', motif: 'plusieurs_docs_code' }),
  ]);
  expect(m.qa('[data-testid^="v532-a-verifier-"]').length).toBe(2);
  expect(m.q('[data-testid="v532-badge-averifier-d1"]').textContent).toMatch(/À vérifier/);
  expect(m.qa('[data-testid^="v532-actuel-"]').length).toBe(0);
  expect(m.qa('[data-testid^="promo-code-"]').length).toBe(2);
  m.unmount();
});

test('Codes sans bénéficiaire : liste inchangée, hors regroupement', () => {
  const m = monter([fiche('g1', 'PROMO10', '', 3, 100, '2026-12-31', true, { classement: 'actuel' })]);
  expect(m.q('[data-testid="v532-sans-beneficiaire"]')).toBeTruthy();
  expect(m.qa('[data-testid^="v532-personne-"]').length).toBe(0);
  expect(m.q('[data-testid="promo-code-g1"]')).toBeTruthy();
  m.unmount();
});

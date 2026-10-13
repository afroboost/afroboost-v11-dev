/**
 * V618f — état métier d'un code (écran « Codes » + export CSV) et bouton « Lien ».
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import PromoCodesTab from '../../components/dashboard/PromoCodesTab';
import { etatMetierCode, finAfficheeCode, lienEspaceProposable, dateCodeExpiree } from '../etatCodeV618';

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn() }));
beforeEach(() => { require('axios').get.mockImplementation(() => Promise.resolve({ data: {} })); });
jest.mock('../../components/dashboard/index', () => ({ CreditsGate: ({ children }) => <>{children}</> }));
jest.mock('../../components/SvgIcon', () => ({ name }) => <i data-icon={name} />);

const AUJ = new Date(2026, 9, 13, 10, 0);
const f = (extra) => ({ id: 'x', code: 'X', active: true, expiresAt: '2026-05-05', ...extra });

describe('A. état métier (CSV)', () => {
  test('ancien code expiré, interrupteur actif -> EXPIRÉ (plus « Actif : Oui »)', () => {
    expect(etatMetierCode(f({ v532: { classement: 'historique', motif: 'expire' } }), AUJ)).toBe('EXPIRÉ');
  });
  test('abonnement actuel désigné par le serveur -> ACTIF, même si la fiche porte une vieille date', () => {
    const c = f({ expiresAt: '2026-09-30', v532: { classement: 'actuel', expire_le: '2027-06-04T23:59:59+00:00' }, v618: { etat: 'actuel' } });
    expect(etatMetierCode(c, AUJ)).toBe('ACTIF');
    expect(finAfficheeCode(c)).toBe('2027-06-04');   // le jour seul : jamais le lendemain à l'heure suisse
  });
  test('remplacé / épuisé non expiré -> HISTORIQUE', () => {
    expect(etatMetierCode(f({ expiresAt: '2027-01-01', v532: { classement: 'historique', motif: 'remplace' } }), AUJ)).toBe('HISTORIQUE');
  });
  test('conflit (plusieurs abonnements actuels) ou doublons à vérifier -> CONFLIT', () => {
    expect(etatMetierCode(f({ expiresAt: '2027-06-04', v532: { classement: 'actuel' }, v618: { etat: 'conflit' } }), AUJ)).toBe('CONFLIT');
    expect(etatMetierCode(f({ expiresAt: '2027-06-04', v532: { classement: 'a_verifier' } }), AUJ)).toBe('CONFLIT');
  });
  test('repli sans étiquette serveur : actif + date future -> ACTIF ; date passée -> EXPIRÉ', () => {
    expect(etatMetierCode(f({ expiresAt: '2027-01-01' }), AUJ)).toBe('ACTIF');
    expect(etatMetierCode(f({}), AUJ)).toBe('EXPIRÉ');
  });
  test('règle du jour : la date du jour reste valable', () => {
    expect(dateCodeExpiree('2026-10-13', AUJ)).toBe(false);
    expect(dateCodeExpiree('2026-10-12', AUJ)).toBe(true);
  });
});

describe('B. bouton « Lien »', () => {
  test('jamais sur un code expiré / historique / en conflit / inactif', () => {
    expect(lienEspaceProposable(f({ v532: { classement: 'historique' } }), AUJ)).toBe(false);
    expect(lienEspaceProposable(f({ expiresAt: '2027-01-01', v532: { classement: 'historique', motif: 'remplace' } }), AUJ)).toBe(false);
    expect(lienEspaceProposable(f({ expiresAt: '2027-01-01', v532: { classement: 'actuel' }, v618: { etat: 'conflit' } }), AUJ)).toBe(false);
    expect(lienEspaceProposable(f({ active: false, expiresAt: '2027-01-01', v532: { classement: 'actuel' } }), AUJ)).toBe(false);
  });
  test('proposé pour l\'abonnement actuel', () => {
    expect(lienEspaceProposable(f({ expiresAt: '2027-01-01', v532: { classement: 'actuel' } }), AUJ)).toBe(true);
  });
});

const base = {
  hasCreditsFor: () => true, servicePrices: {}, coachCredits: 99, setTab: () => {},
  codesSearch: '', setCodesSearch: () => {}, newCode: { courses: [], assignedEmails: [] }, setNewCode: () => {},
  isBatchMode: false, setIsBatchMode: () => {}, batchLoading: false,
  showManualContactForm: false, setShowManualContactForm: () => {}, manualContact: {}, setManualContact: () => {},
  uniqueCustomers: [], selectedBeneficiaries: [], toggleBeneficiarySelection: () => {},
  courses: [], offers: [], toggleCourseSelection: () => {}, removeAllowedArticle: () => {},
  addCode: () => {}, deleteCode: () => {}, toggleCode: () => {}, duplicateCode: () => {}, editCode: () => {},
  addManualContact: () => {}, handleImportCSV: () => {}, exportPromoCodesCSV: () => {}, manualSanitize: () => {},
  editingCode: null, t: (k) => k,
};
function monter(props) {
  const div = document.createElement('div'); document.body.appendChild(div);
  const root = createRoot(div);
  act(() => { root.render(<PromoCodesTab {...base} {...props} />); });
  return { q: (s) => div.querySelector(s), texte: () => div.textContent, unmount: () => act(() => root.unmount()) };
}

describe('C. écran « Codes » (rendu réel)', () => {
  const codes = [
    // ancien code expiré resté « active » (les 20 fiches historiques)
    { id: 'old', code: 'ANCIEN-26', assignedEmail: 'a@t.example', used: 8, maxUses: 9, expiresAt: '2026-09-01', active: true,
      v532: { classement: 'historique', motif: 'expire' }, v618: { etat: 'historique' } },
    // fiche sans bénéficiaire qui porte l'abonnement actuel (cas BASSBOOSTX-31 : vieille date sur la fiche)
    { id: 'cur', code: 'ACTUEL-31', used: 6, maxUses: 7, expiresAt: '2026-09-30', active: true,
      v532: { classement: 'actuel', motif: 'abonnement_actuel', utilise: 1, total: 32, restant: 31, expire_le: '2027-06-04T23:59:59+00:00' },
      v618: { etat: 'actuel' } },
  ];
  test('ancien code expiré : aucun bouton « Lien »', () => {
    const m = monter({ discountCodes: codes });
    expect(m.q('[data-testid="share-space-link-old"]')).toBeNull();
    m.unmount();
  });
  test('abonnement actuel : bouton « Lien » présent, pas de badge EXPIRÉ sur sa ligne, fin = celle de l\'abonnement', () => {
    const m = monter({ discountCodes: codes });
    expect(m.q('[data-testid="share-space-link-cur"]')).toBeTruthy();
    const ligne = m.q('[data-testid="share-space-link-cur"]').closest('[class*="rounded"]').parentElement.parentElement;
    expect(m.texte()).toMatch(/04\.06\.2027/);
    expect(m.q('button[data-testid="toggle-code-cur"]')).toBeTruthy();   // Actif/Inactif, pas « Expiré »
    expect(ligne).toBeTruthy();
    m.unmount();
  });
});

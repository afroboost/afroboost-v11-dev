/**
 * V617 — abonnements manuels dans « Codes promo » :
 *  - historique en LECTURE SEULE (aucune action ne peut réactiver un ancien abonnement) ;
 *  - articles autorisés rangés par nature, l'inutilisable masqué par défaut, les offres
 *    réservées accessibles par l'option dédiée, l'historique toujours affiché avec badge ;
 *  - suivi de paiement : 400 total / 200 encaissé -> reste 200 ;
 *  - « Modifier l'abonnement actuel » / « Créer le nouvel abonnement ».
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import PromoCodesTab from '../PromoCodesTab';
import { champsModifies, classerArticles, resteAPayer, suiviPourEnvoi, suiviVersFormulaire, messageServeur, typeRefus } from '../../../utils/abonnementsManuels';

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn() }));
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

function monter(props) {
  const div = document.createElement('div'); document.body.appendChild(div);
  const root = createRoot(div);
  act(() => { root.render(<PromoCodesTab {...base} {...props} />); });
  return { q: (s) => div.querySelector(s), qa: (s) => div.querySelectorAll(s), texte: () => div.textContent, unmount: () => act(() => root.unmount()) };
}

const fiche = (id, code, email, used, max, exp, active, v532, extra = {}) => ({ id, code, assignedEmail: email, used, maxUses: max, expiresAt: exp, active, v532, ...extra });
const AU = 'aurelie@exemple.test';

describe('A / D. Un seul abonnement actuel, historique en lecture seule', () => {
  const codes = [
    fiche('h1', 'BASSBOOSTX-01', AU, 4, 47, '2026-05-05', true, { classement: 'historique', motif: 'expire' }),
    fiche('h2', 'AurelieBoost-26', AU, 8, 9, '2026-09-01', true, { classement: 'historique', motif: 'expire' }),
    fiche('h3', 'AFR-2287CA', AU, 7, 10, '2026-10-11', true, { classement: 'historique', motif: 'expire' }),
    fiche('h4', 'ANCIEN-REMPLACE', AU, 2, 10, '2027-01-01', true, { classement: 'historique', motif: 'remplace' }),
    fiche('a1', 'AURE-8M', AU, 1, 31, '2027-06-07', true, { classement: 'actuel', motif: 'unique', utilise: 1, total: 31, restant: 30 },
      { v617_abonnement: { id: 's-new', statut: 'active', motif: 'unique', historiques: 0, suivi: {} } }),
  ];
  test('4 anciens + 1 actuel -> zone principale = 1 seul ; Historique (4) replié', () => {
    const m = monter({ discountCodes: codes });
    expect(m.qa('[data-testid^="v532-actuel-"]').length).toBe(1);
    expect(m.q('[data-testid="v532-actuel-a1"]')).toBeTruthy();
    const hist = m.q(`[data-testid="v532-historique-${AU}"]`);
    expect(hist.tagName).toBe('DETAILS');
    expect(hist.open).toBe(false);
    expect(hist.querySelector('summary').textContent).toMatch(/Historique \(4\)/);
    m.unmount();
  });
  test('les 4 anciens : lecture seule — ni Éditer, ni Actif/Inactif, ni Supprimer', () => {
    const m = monter({ discountCodes: codes });
    ['h1', 'h2', 'h3', 'h4'].forEach((id) => {
      expect(m.q(`[data-testid="v617-lecture-seule-${id}"]`)).toBeTruthy();
      expect(m.q(`[data-testid="edit-code-${id}"]`)).toBeNull();
      expect(m.q(`[data-testid="delete-code-${id}"]`)).toBeNull();
      expect(m.q(`button[data-testid="toggle-code-${id}"]`)).toBeNull();
    });
    expect(m.q('[data-testid="edit-code-a1"]')).toBeTruthy();
    expect(m.q('[data-testid="v617-deverrouiller-h1"]')).toBeNull();   // pas super-admin -> pas de déverrouillage
    m.unmount();
  });
  test('badges clairs : Expiré / Remplacé', () => {
    const m = monter({ discountCodes: codes });
    expect(m.texte()).toMatch(/EXPIRÉ/);
    expect(m.texte()).toMatch(/REMPLACÉ/);
    m.unmount();
  });
  test('super-admin : déverrouillage seulement après avoir retapé le nom du code', () => {
    const promptSpy = jest.spyOn(window, 'prompt').mockReturnValueOnce('mauvais').mockReturnValueOnce('BASSBOOSTX-01');
    const m = monter({ discountCodes: codes, isSuperAdmin: true });
    act(() => { m.q('[data-testid="v617-deverrouiller-h1"]').click(); });
    expect(m.q('[data-testid="edit-code-h1"]')).toBeNull();
    act(() => { m.q('[data-testid="v617-deverrouiller-h1"]').click(); });
    expect(m.q('[data-testid="edit-code-h1"]')).toBeTruthy();
    promptSpy.mockRestore();
    m.unmount();
  });
  test('client sans abonnement actuel -> « Créer un nouvel abonnement » (jamais une réactivation)', () => {
    const nouvel = jest.fn();
    const m = monter({ discountCodes: codes.slice(0, 4), nouvelAbonnementPour: nouvel });
    act(() => { m.q(`[data-testid="v617-nouvel-abonnement-${AU}"]`).click(); });
    expect(nouvel).toHaveBeenCalledTimes(1);
    m.unmount();
  });
});

describe('Libellés : modifier l\'actuel / créer un nouvel abonnement', () => {
  test('édition d\'un code qui a un abonnement actuel -> « Modifier l\'abonnement actuel » + bandeau', () => {
    const c = fiche('a1', 'AURE-8M', AU, 1, 31, '2027-06-07', true, { classement: 'actuel' },
      { v617_abonnement: { id: 's', motif: 'unique', historiques: 3, suivi: {} } });
    const m = monter({ discountCodes: [c], editingCode: 'a1', newCode: { code: 'AURE-8M', courses: [], assignedEmails: [AU] } });
    expect(m.q('[data-testid="add-code"]').textContent).toMatch(/Modifier l'abonnement actuel/);
    expect(m.q('[data-testid="v617-bandeau-edition"]').textContent).toMatch(/Seul l'abonnement actuel sera modifié\. 3 ancien/);
    m.unmount();
  });
  test('plusieurs abonnements actuels -> le bandeau annonce l\'erreur d\'intégrité', () => {
    const c = fiche('d', 'DOUBLE', AU, 1, 10, '2027-06-07', true, { classement: 'actuel' }, { v617_abonnement: { id: null, motif: 'plusieurs', historiques: 2, suivi: {} } });
    const m = monter({ discountCodes: [c], editingCode: 'd', newCode: { code: 'DOUBLE', courses: [], assignedEmails: [AU] } });
    expect(m.q('[data-testid="v617-bandeau-edition"]').textContent).toMatch(/Erreur d'intégrité/);
    m.unmount();
  });
  test('création avec bénéficiaire -> « Créer le nouvel abonnement » + section paiement', () => {
    const m = monter({ discountCodes: [], selectedBeneficiaries: [AU],
      newCode: { courses: [], assignedEmails: [AU], montant_encaisse: 200, origine_paiement: 'twint',
        suivi_paiement: { montant_total: 400, plusieurs_fois: true, nb_paiements: 2, paiement_actuel: 1, prochaine_echeance: '2026-11-07', note_interne: '' } } });
    expect(m.q('[data-testid="add-code"]').textContent).toMatch(/Créer le nouvel abonnement/);
    expect(m.q('[data-testid="v617-suivi-paiement"]')).toBeTruthy();
    expect(m.q('[data-testid="v617-reste"]').textContent).toBe('200.00 CHF');
    expect(m.q('[data-testid="v617-paiement-actuel"]').value).toBe('1');
    m.unmount();
  });
  test('code promo simple (sans bénéficiaire) -> pas de section paiement', () => {
    const m = monter({ discountCodes: [], selectedBeneficiaries: [] });
    expect(m.q('[data-testid="v617-suivi-paiement"]')).toBeNull();
    m.unmount();
  });
});

describe('H / I. Articles autorisés par nature', () => {
  const courses = [
    { id: 'c-mer', name: 'Cours à l\'unité', weekday: 3 },
    { id: 'c-arch', name: 'Ancien cours', weekday: 1, archived: true },
    { id: 'c-masq', name: 'Cours masqué', weekday: 5, visible: false },
    { id: 'c-evt', name: 'SILENT 28/10', date: '2026-10-28' },
    { id: 'c-evt-fini', name: 'LAFF', date: '2026-08-01' },
  ];
  const offers = [
    { id: 'o-pulse', name: 'PULSE x10 cours' },
    { id: 'o-membres', name: 'Membres', visible: false },
    { id: 'o-tshirt', name: 'T-shirt', isProduct: true },
    { id: 'o-evt', name: 'ÉDITION SPÉCIALE', offer_type: 'event', linked_course_ids: ['c-evt'] },
    { id: 'o-arch', name: 'Offre archivée', archived: true },
  ];
  const j = '2026-10-12';
  test('par défaut : seul l\'utilisable, rangé en cours / événements / offres / articles', () => {
    const r = classerArticles({ courses, offers, aujourdhui: j });
    expect(r.cours.map(x => x.id)).toEqual(['c-mer']);
    expect(r.evenements.map(x => x.id).sort()).toEqual(['c-evt', 'o-evt']);
    expect(r.offres.map(x => x.id)).toEqual(['o-pulse']);
    expect(r.articles.map(x => x.id)).toEqual(['o-tshirt']);
    expect(r.masques).toBe(5);
  });
  test('I. l\'offre réservée aux membres n\'apparaît qu\'avec l\'option dédiée (jamais l\'archivée)', () => {
    const r = classerArticles({ courses, offers, afficherInternes: true, aujourdhui: j });
    expect(r.offres.map(x => x.id)).toEqual(['o-pulse', 'o-membres']);
    expect(r.offres.find(x => x.id === 'o-membres').badge).toBe('Réservée / interne');
    expect(r.cours.map(x => x.id)).toEqual(['c-mer', 'c-masq']);
    expect([...r.offres, ...r.cours].some(x => x.id === 'o-arch' || x.id === 'c-arch')).toBe(false);
  });
  test('E. un élément DÉJÀ choisi reste visible avec son badge (historique conservé)', () => {
    const r = classerArticles({ courses, offers, selection: ['o-arch', 'c-evt-fini', 'o-membres'], aujourdhui: j });
    expect(r.offres.find(x => x.id === 'o-arch').badge).toBe('Archivée');
    expect(r.evenements.find(x => x.id === 'c-evt-fini').badge).toBe('Terminé');
    expect(r.offres.find(x => x.id === 'o-membres').selectionne).toBe(true);
  });
  test('rendu : rubriques séparées + case « Afficher les offres réservées / internes »', () => {
    const m = monter({ discountCodes: [], courses, offers });
    expect(m.q('[data-testid="v617-rubrique-cours"]')).toBeTruthy();
    expect(m.q('[data-testid="v617-rubrique-evenements"]')).toBeTruthy();
    expect(m.q('[data-testid="v617-rubrique-articles"]')).toBeTruthy();
    expect(m.q('[data-testid="offer-select-o-membres"]')).toBeNull();
    act(() => { m.q('[data-testid="v617-afficher-internes"]').click(); });
    expect(m.q('[data-testid="offer-select-o-membres"]')).toBeTruthy();
    expect(m.q('[data-testid="offer-select-o-arch"]')).toBeNull();
    m.unmount();
  });
});

describe('J / C. Règles pures', () => {
  test('J. reste à payer : 400 - 200 = 200', () => {
    expect(resteAPayer(400, 200)).toBe(200);
    expect(resteAPayer('', 200)).toBeNull();
    expect(resteAPayer(400, 450)).toBe(0);
  });
  test('suivi : formulaire <-> envoi ; vide -> rien n\'est envoyé', () => {
    expect(suiviPourEnvoi(suiviVersFormulaire(null))).toBeNull();
    expect(suiviPourEnvoi({ montant_total: '400', plusieurs_fois: true, nb_paiements: '2', paiement_actuel: '1', prochaine_echeance: '2026-11-07', note_interne: ' 2e paiement ' }))
      .toEqual({ montant_total: 400, plusieurs_fois: true, nb_paiements: 2, paiement_actuel: 1, prochaine_echeance: '2026-11-07', note_interne: '2e paiement' });
  });
  test('C. seuls les champs réellement modifiés partent au serveur', () => {
    const original = { maxUses: 31, expiresAt: '2027-06-07', used: 1, courses: ['b', 'a'], montant_encaisse: 200, origine_paiement: 'twint' };
    expect(champsModifies({ maxUses: 31, expiresAt: '2027-06-07', courses: ['a', 'b'], montant_encaisse: 200, origine_paiement: 'twint' }, original)).toEqual({});
    expect(champsModifies({ maxUses: 32, expiresAt: '2027-06-07' }, original)).toEqual({ maxUses: 32 });
    expect(champsModifies({ used: 0 }, original)).toEqual({ used: 0 });
  });
  test('refus serveur lisibles (détail objet V617)', () => {
    const err = { response: { status: 409, data: { detail: { type: 'droits_existants', message: 'Ce client a encore…' } } } };
    expect(typeRefus(err)).toBe('droits_existants');
    expect(messageServeur(err)).toBe('Ce client a encore…');
    expect(messageServeur({ response: { data: { detail: 'texte' } } })).toBe('texte');
  });
});

// ═══ V617d — « Suivi du paiement » sur TOUS les abonnements éditables ═══════════
describe('V617d. Suivi du paiement visible partout, rien d\'inventé', () => {
  const { etatSuiviPaiement } = require('../../../utils/abonnementsManuels');
  const CH = 'christelle@exemple.test';
  // Ancien code sans bénéficiaire sur la fiche (comme CHRISTOUX10) : le lien au client
  // ne passe que par la souscription.
  const ancien = (motif, extra = {}) => fiche('c10', 'Christoux10', null, 11, 67, '2027-05-25', true, { classement: 'actuel' },
    { montant_encaisse: 400, origine_paiement: 'twint',
      v617_abonnement: { id: motif === 'unique' ? 's-c10' : null, motif, historiques: 0, suivi: {} }, ...extra });
  const editer = (c, newCode = {}) => monter({ discountCodes: [c], editingCode: c.id, selectedBeneficiaries: [],
    newCode: { code: c.code, courses: [], assignedEmails: [], montant_encaisse: 400, origine_paiement: 'twint',
      suivi_paiement: suiviVersFormulaire(c.v617_abonnement && c.v617_abonnement.suivi), ...newCode } });

  test('A. abonnement V617 récent avec suivi -> données intactes', () => {
    const suivi = { montant_total: 400, plusieurs_fois: true, nb_paiements: 2, paiement_actuel: 1, prochaine_echeance: '2026-11-07', note_interne: 'Deuxième versement' };
    const c = fiche('a8', 'AURELIE-8M', AU, 0, 64, '2027-06-07', true, { classement: 'actuel' },
      { v617_abonnement: { id: 's-a8', motif: 'unique', historiques: 0, suivi } });
    const m = monter({ discountCodes: [c], editingCode: 'a8', selectedBeneficiaries: [AU],
      newCode: { code: 'AURELIE-8M', courses: [], assignedEmails: [AU], montant_encaisse: 200, origine_paiement: 'twint', suivi_paiement: suiviVersFormulaire(suivi) } });
    expect(m.q('[data-testid="v617-montant-total"]').value).toBe('400');
    expect(m.q('[data-testid="v617-reste"]').textContent).toBe('200.00 CHF');
    expect(m.q('[data-testid="v617-echeance"]').value).toBe('2026-11-07');
    expect(m.q('[data-testid="v617-note-interne"]').value).toBe('Deuxième versement');
    expect(m.q('[data-testid="v617-suivi-bloque"]')).toBeNull();
    m.unmount();
  });

  test('B / E. ancien abonnement sans suivi ni bénéficiaire sur la fiche -> bloc visible, champs inconnus vides', () => {
    const m = editer(ancien('unique'));
    expect(m.q('[data-testid="v617-suivi-paiement"]')).toBeTruthy();
    expect(m.q('[data-testid="v617-montant-total"]').value).toBe('');
    expect(m.q('[data-testid="v617-echeance"]').value).toBe('');
    expect(m.q('[data-testid="v617-note-interne"]').value).toBe('');
    expect(m.q('[data-testid="v617-plusieurs-fois"]').checked).toBe(false);
    expect(m.q('[data-testid="v617-montant-total"]').disabled).toBe(false);
    m.unmount();
  });

  test('C. encaissé prérempli depuis la donnée réelle, total NON inventé, reste « — »', () => {
    const m = editer(ancien('unique'));
    expect(m.q('[data-testid="v617-encaisse"]').textContent).toBe('400 CHF');
    expect(m.q('[data-testid="v617-reste"]').textContent).toBe('—');
    m.unmount();
  });

  test('D. total 400 / encaissé 200 -> reste 200 ; total sans encaissé -> non calculé', () => {
    expect(resteAPayer(400, 200)).toBe(200);
    expect(resteAPayer(400, '')).toBeNull();
    expect(resteAPayer(400, undefined)).toBeNull();
    expect(resteAPayer('', '')).toBeNull();
    expect(resteAPayer(100, 0)).toBe(100);         // offert / 0 connu : calculable
  });

  test('F. plusieurs abonnements actuels -> bloc visible, verrouillé, message clair', () => {
    const m = editer(ancien('plusieurs'));
    expect(m.q('[data-testid="v617-suivi-paiement"]')).toBeTruthy();
    expect(m.q('[data-testid="v617-suivi-bloque"]').textContent)
      .toMatch(/Plusieurs abonnements actuels détectés\. Aucune modification ne sera enregistrée tant que ce doublon n'aura pas été résolu\./);
    expect(m.q('[data-testid="v617-suivi-paiement"] fieldset').disabled).toBe(true);
    m.unmount();
  });

  test('G. aucun abonnement actuel (historique) -> lecture seule', () => {
    const e = etatSuiviPaiement({ editingCode: 'x', fiche: { v617_abonnement: { motif: 'aucun' } }, beneficiaires: [] });
    expect(e).toMatchObject({ visible: true, editable: false });
    const m = editer(ancien('aucun'));
    expect(m.q('[data-testid="v617-suivi-paiement"] fieldset').disabled).toBe(true);
    m.unmount();
  });

  test('paiement unique ou en plusieurs fois : la case et la note sont toujours là', () => {
    const m = editer(ancien('unique'));
    expect(m.q('[data-testid="v617-plusieurs-fois"]')).toBeTruthy();
    expect(m.q('[data-testid="v617-note-interne"]')).toBeTruthy();
    expect(m.q('[data-testid="v617-paiement-actuel"]')).toBeNull();     // décoché : ni nombre ni paiement actuel
    m.unmount();
    const m2 = editer(ancien('unique'), { suivi_paiement: { ...suiviVersFormulaire(null), plusieurs_fois: true } });
    expect(m2.q('[data-testid="v617-paiement-actuel"]')).toBeTruthy();
    expect(m2.q('[data-testid="v617-nb-paiements"]')).toBeTruthy();
    m2.unmount();
  });

  test('code promo simple (aucun abonnement) en édition -> pas de bloc ; mode série -> pas de bloc', () => {
    expect(etatSuiviPaiement({ editingCode: 'p', fiche: {}, beneficiaires: [] }).visible).toBe(false);
    expect(etatSuiviPaiement({ isBatchMode: true, beneficiaires: [CH] }).visible).toBe(false);
    expect(etatSuiviPaiement({ editingCode: null, beneficiaires: [CH] })).toMatchObject({ visible: true, editable: true });
  });

  test('H. ouvrir une fiche n\'envoie AUCUNE requête d\'écriture', () => {
    const axios = require('axios');
    axios.put.mockClear(); axios.post.mockClear();
    const m = editer(ancien('unique'));
    expect(axios.put).not.toHaveBeenCalled();
    expect(axios.post).not.toHaveBeenCalled();
    m.unmount();
  });
});

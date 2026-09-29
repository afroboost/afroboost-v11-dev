/**
 * Invitation (page Campagnes) — fonctions pures + URL des appels.
 * axios est mocké : aucun réseau.
 */
import axios from 'axios';
import {
  racineApi, offresPourType, paliersOffre, heureDuCours, prochaineDate, construireOccurrence,
  formulaireInitial, construireCorps, validerInvitation, texteWhatsAppCampagne, partageable,
  messageErreur, creerInvitation, modifierInvitation, lireOptions, lireApercuBrouillon,
  CTA_DEFAUT, TEXTE_RECONNEXION, TEXTE_FUSEAU_PALIERS, CHAMPS_CONTENU,
} from '../invitationCampagne';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn() },
}));

beforeEach(() => { axios.get.mockReset(); axios.post.mockReset(); axios.put.mockReset(); });

const OFFRES = [
  { id: 'free1', name: 'Essai', price: 0, is_free: true },
  { id: 'pay1', name: 'Soirée', price: 30, is_free: false, has_progressive_pricing: true,
    price_early_bird: 20, price_standard: 30, price_last_minute: 40 },
  { id: 'pay2', name: 'Stage', price: 25, is_free: false },
];
const INTERDITS = ['recipients', 'channel', 'send_at', 'scheduledAt', 'coach_id'];

describe('racineApi', () => {
  test('jamais /api/api', () => {
    expect(racineApi('')).toBe('');
    expect(racineApi('https://afroboost.com/')).toBe('https://afroboost.com');
    expect(racineApi('https://afroboost.com/api')).toBe('https://afroboost.com');
    expect(racineApi(undefined)).toBe('');
  });
});

describe('offres et paliers', () => {
  test('offresPourType filtre gratuites / payantes / aucune', () => {
    expect(offresPourType('trial', OFFRES).map((o) => o.id)).toEqual(['free1']);
    expect(offresPourType('event_free', OFFRES).map((o) => o.id)).toEqual(['free1']);
    expect(offresPourType('event_paid', OFFRES).map((o) => o.id)).toEqual(['pay1', 'pay2']);
    expect(offresPourType('pass_duo', OFFRES)).toEqual([]);
  });
  test('paliersOffre : 3 paliers ordonnés, ou le prix seul', () => {
    expect(paliersOffre(OFFRES[1]).map((p) => [p.libelle, p.prix]))
      .toEqual([['Prévente', 20], ['Standard', 30], ['Dernière minute', 40]]);
    expect(paliersOffre(OFFRES[2])).toEqual([{ cle: 'prix', libelle: 'Prix', prix: 25 }]);
    expect(paliersOffre({ has_progressive_pricing: true, price_standard: 30 }).length).toBe(1);
  });
});

describe('dates et heures', () => {
  test('heureDuCours normalise', () => {
    expect(heureDuCours('18:30')).toBe('18:30');
    expect(heureDuCours('9h05')).toBe('09:05');
    expect(heureDuCours('18:30:00')).toBe('18:30');
    expect(heureDuCours('abc')).toBe('');
    expect(heureDuCours('25:00')).toBe('');
  });
  test('prochaineDate : 0 = dimanche, aujourd\'hui compris', () => {
    expect(prochaineDate(0, '2026-09-27')).toBe('2026-09-27'); // dimanche
    expect(prochaineDate(3, '2026-09-27')).toBe('2026-09-30'); // mercredi suivant
    expect(prochaineDate(null, '2026-09-27')).toBe('');
  });
  test('construireOccurrence = YYYY-MM-DDTHH:MM', () => {
    expect(construireOccurrence('2026-10-04', '18:30')).toBe('2026-10-04T18:30');
    expect(construireOccurrence('2026-10-04', '')).toBe('');
  });
});

describe('construireCorps — liste blanche', () => {
  test('trial : cours, occurrence, offre ; aucun champ interdit', () => {
    const c = construireCorps({ ...formulaireInitial('trial'), course_id: 'c1', date: '2026-10-04', heure: '18:30', offer_id: 'free1' });
    expect(Object.keys(c).sort()).toEqual(CHAMPS_CONTENU.slice().sort());
    expect(c).toMatchObject({ type: 'trial', course_id: 'c1', occurrence: '2026-10-04T18:30', offer_id: 'free1', cta_label: CTA_DEFAUT.trial });
    INTERDITS.forEach((k) => expect(c).not.toHaveProperty(k));
  });
  test('pass_duo : jamais d\'offre', () => {
    const c = construireCorps({ ...formulaireInitial('pass_duo'), course_id: 'c1', date: '2026-10-04', heure: '18:30', offer_id: 'free1' });
    expect(c.offer_id).toBeNull();
  });
});

describe('validerInvitation', () => {
  const J = '2026-09-29';
  test('titre vide → erreur', () => {
    const e = validerInvitation({ ...formulaireInitial('pass_duo'), title: '  ', course_id: 'c1', date: '2026-10-04', heure: '18:30' }, OFFRES, J);
    expect(e.title).toBeTruthy();
  });
  test('trial sans cours / offre → erreurs', () => {
    const e = validerInvitation(formulaireInitial('trial'), OFFRES, J);
    expect(e.course_id).toBeTruthy();
    expect(e.date).toBeTruthy();
    expect(e.offer_id).toBeTruthy();
  });
  test('trial complet → valide', () => {
    expect(validerInvitation({ ...formulaireInitial('trial'), course_id: 'c1', date: '2026-10-04', heure: '18:30', offer_id: 'free1' }, OFFRES, J)).toEqual({});
  });
  test('event_free : offre gratuite obligatoire, cours facultatif ; date sans heure refusée', () => {
    expect(validerInvitation({ ...formulaireInitial('event_free'), offer_id: 'free1' }, OFFRES, J)).toEqual({});
    expect(validerInvitation({ ...formulaireInitial('event_free'), offer_id: 'pay1' }, OFFRES, J).offer_id).toBeTruthy();
    expect(validerInvitation({ ...formulaireInitial('event_free'), offer_id: 'free1', date: '2026-10-04' }, OFFRES, J).heure).toBeTruthy();
  });
  test('event_paid : offre payante obligatoire', () => {
    expect(validerInvitation(formulaireInitial('event_paid'), OFFRES, J).offer_id).toBeTruthy();
    expect(validerInvitation({ ...formulaireInitial('event_paid'), offer_id: 'free1' }, OFFRES, J).offer_id).toBeTruthy();
    expect(validerInvitation({ ...formulaireInitial('event_paid'), offer_id: 'pay1' }, OFFRES, J)).toEqual({});
  });
  test('CTA > 30 caractères refusé (aligné sur le serveur)', () => {
    const base = { ...formulaireInitial('event_free'), offer_id: 'free1' };
    expect(validerInvitation({ ...base, cta_label: 'x'.repeat(30) }, OFFRES, J)).toEqual({});
    expect(validerInvitation({ ...base, cta_label: 'x'.repeat(31) }, OFFRES, J).cta_label).toBeTruthy();
    expect(construireCorps({ ...base, cta_label: 'y'.repeat(50) }).cta_label.length).toBe(30);
  });
  test('date passée refusée', () => {
    const e = validerInvitation({ ...formulaireInitial('pass_duo'), course_id: 'c1', date: '2026-09-01', heure: '18:30' }, OFFRES, J);
    expect(e.date).toMatch(/passée/);
  });
});

describe('partage et erreurs', () => {
  test('texte WhatsApp = message + share_url (?v inclus)', () => {
    const dto = { message: 'Viens !', share_url: 'https://afroboost.com/i/TOK?v=3' };
    expect(texteWhatsAppCampagne(dto)).toBe('Viens !\nhttps://afroboost.com/i/TOK?v=3');
    expect(texteWhatsAppCampagne({ title: 'Titre', share_url: 'u' })).toBe('Titre\nu');
  });
  test('partageable : actif + lien, jamais event_paid', () => {
    expect(partageable({ status: 'active', share_url: 'u', type: 'trial' })).toBe(true);
    expect(partageable({ status: 'draft', share_url: 'u', type: 'trial' })).toBe(false);
    expect(partageable({ status: 'active', share_url: 'u', type: 'event_paid' })).toBe(false);
  });
  test('401/403 → reconnexion ; 409 activation → fuseau', () => {
    expect(messageErreur({ response: { status: 401 } })).toBe(TEXTE_RECONNEXION);
    expect(messageErreur({ response: { status: 403 } })).toBe(TEXTE_RECONNEXION);
    expect(messageErreur({ response: { status: 409 } }, 'activation')).toBe(TEXTE_FUSEAU_PALIERS);
  });
});

describe('appels API', () => {
  test('URL cohérentes et corps propres', async () => {
    axios.get.mockResolvedValue({ data: { courses: [{ id: 'c1' }], offers: [] } });
    axios.post.mockResolvedValue({ data: { id: 'i1' } });
    axios.put.mockResolvedValue({ data: { id: 'i1' } });
    await lireOptions('https://x.ch/api');
    expect(axios.get.mock.calls[0][0]).toBe('https://x.ch/api/referral/campaigns/options');
    await creerInvitation('', { ...construireCorps(formulaireInitial('pass_duo')), recipients: ['x'] });
    expect(axios.post.mock.calls[0][0]).toBe('/api/referral/campaigns');
    expect(axios.post.mock.calls[0][1].status).toBe('draft');
    expect(axios.post.mock.calls[0][1]).not.toHaveProperty('recipients');
    await modifierInvitation('', 'i1', { title: 'T', type: 'trial', channel: 'x', status: 'active' });
    expect(axios.put.mock.calls[0][0]).toBe('/api/referral/campaigns/i1');
    expect(axios.put.mock.calls[0][1]).toEqual({ title: 'T', status: 'active' });
    axios.get.mockResolvedValue({ data: 'blob' });
    await lireApercuBrouillon('', 'i1');
    expect(axios.get.mock.calls[1][0]).toBe('/api/share/invite-preview/i1.jpg');
    expect(axios.get.mock.calls[1][1].responseType).toBe('blob');
  });
});

// INV-5 — la modale ne propose que ce que le lien profond peut réellement ouvrir.
describe('INV-5 — offres ouvrables et cours de l’offre', () => {
  // eslint-disable-next-line global-require
  const M = require('../invitationCampagne');
  const COURS = [
    { id: 'c1', name: 'Dimanche', time: '18:30', weekday: 0, public: true },
    { id: 'c2', name: 'Mercredi', time: '19:15', weekday: 3, public: true },
    { id: 'c3', name: 'Archivé', time: '18:30', weekday: 0, public: false },
  ];
  const OFF = [
    { id: 'lie', price: 0, is_free: true, openable: true, course_ids: ['c1'] },
    { id: 'libre', price: 0, is_free: true, openable: true, course_ids: [] },
    { id: 'cachee', price: 0, is_free: true, openable: false, course_ids: [] },
    { id: 'morte', price: 0, is_free: true, openable: true, course_ids: ['c3'] },
  ];
  test('trial : offres ouvrables ET avec au moins un cours public ; event_free : ouvrables', () => {
    expect(offresPourType('trial', OFF, COURS).map((o) => o.id)).toEqual(['lie', 'libre']);
    expect(offresPourType('event_free', OFF, COURS).map((o) => o.id)).toEqual(['lie', 'libre', 'morte']);
  });
  test('cours proposés : ceux de l’offre, publics ; offre sans cours liés -> tous les publics', () => {
    expect(M.coursPourInvitation('trial', OFF[0], COURS).map((c) => c.id)).toEqual(['c1']);
    expect(M.coursPourInvitation('trial', OFF[1], COURS).map((c) => c.id)).toEqual(['c1', 'c2']);
    expect(M.coursPourInvitation('trial', null, COURS).map((c) => c.id)).toEqual(['c1', 'c2']);
    expect(M.coursPourInvitation('pass_duo', OFF[0], COURS).map((c) => c.id)).toEqual(['c1', 'c2', 'c3']);
  });
  test('validation : cours hors offre, offre non ouvrable, date hors séance', () => {
    const base = { type: 'trial', title: 'T', cta_label: 'Go', date: '2030-10-06', heure: '18:30' };
    expect(validerInvitation({ ...base, offer_id: 'lie', course_id: 'c1' }, OFF, '2030-01-01', COURS)).toEqual({});
    expect(validerInvitation({ ...base, offer_id: 'lie', course_id: 'c2', heure: '19:15' }, OFF, '2030-01-01', COURS).course_id).toBeTruthy();
    expect(validerInvitation({ ...base, offer_id: 'cachee', course_id: 'c1' }, OFF, '2030-01-01', COURS).offer_id).toBeTruthy();
    expect(validerInvitation({ ...base, offer_id: 'lie', course_id: 'c1', date: '2030-10-07' }, OFF, '2030-01-01', COURS).date).toBeTruthy();
    expect(validerInvitation({ ...base, offer_id: 'lie', course_id: 'c1', heure: '19:00' }, OFF, '2030-01-01', COURS).heure).toBeTruthy();
  });
});

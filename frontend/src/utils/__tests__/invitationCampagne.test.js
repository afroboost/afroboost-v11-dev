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
  resumeErreurs, apercuDepuisFormulaire,
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
    // V607 : date, heure et lieu obligatoires ; le message nomme le champ.
    const e = validerInvitation({ ...formulaireInitial('event_paid'), offer_id: 'pay2' }, OFFRES, J);
    expect(Object.keys(e).sort()).toEqual(['date', 'heure', 'lieu']);
    expect(validerInvitation({ ...formulaireInitial('event_paid'), offer_id: 'pay2', date: '2026-10-20', heure: '20:00', lieu: 'Salle' }, OFFRES, J)).toEqual({});
    // offre à paliers SANS date d'événement (aucun prix actif) : refusée
    expect(validerInvitation({ ...formulaireInitial('event_paid'), offer_id: 'pay1', date: '2026-10-20', heure: '20:00', lieu: 'Salle' }, OFFRES, J).offer_id).toMatch(/date d'événement/);
  });
  test('V607 event_paid : abonnement / offre privée refusés comme billet ; liste filtrée', () => {
    const offres = [{ id: 'abo', name: 'Abo', price: 89, billet: false, raison_non_billet: 'abonnement' },
      { id: 'ev', name: 'Gala', price: 30, billet: true }, { id: 'gratuit', name: 'Essai', price: 0 }];
    expect(offresPourType('event_paid', offres).map((o) => o.id)).toEqual(['ev']);
    expect(offresPourType('trial', offres).map((o) => o.id)).toEqual(['gratuit']); // autres types intacts
    const e = validerInvitation({ ...formulaireInitial('event_paid'), offer_id: 'abo', date: '2026-10-20', heure: '20:00', lieu: 'S' }, offres, J);
    expect(e.offer_id).toMatch(/billet/);
  });
  test('V607 event_paid à paliers : date = celle de l\'événement de l\'offre', () => {
    const offres = [{ id: 'g', name: 'Gala', price: 0, billet: true, has_progressive_pricing: true, countdown_date: '2026-10-25', countdown_time: '20:00',
      prix_actif: { prix: 25, palier: 'early_bird', libelle: 'Tarif lancement', paliers: [] } }];
    const base = { ...formulaireInitial('event_paid'), offer_id: 'g', heure: '20:00', lieu: 'S' };
    expect(validerInvitation({ ...base, date: '2026-10-20' }, offres, J).date).toMatch(/2026-10-25/);
    expect(validerInvitation({ ...base, date: '2026-10-25' }, offres, J)).toEqual({});
  });
  test('V607 resumeErreurs nomme les champs', () => {
    expect(resumeErreurs({ date: 'x', heure: 'y', lieu: 'z' })).toBe("À compléter : la date, l'heure et le lieu.");
    expect(resumeErreurs({})).toBe('');
  });
  test('V607 aperçu : jamais 0 CHF ; Offert / Gratuit / prix actif', () => {
    expect(apercuDepuisFormulaire({ type: 'trial' }).mention_prix).toBe('Offert');
    expect(apercuDepuisFormulaire({ type: 'event_free' }).mention_prix).toBe('Gratuit');
    expect(apercuDepuisFormulaire({ type: 'pass_duo' }).mention_prix).toBe(null);
    expect(apercuDepuisFormulaire({ type: 'event_paid', date: '2026-10-25', heure: '20:00' },
      { prix_actif: { prix: 25, palier: 'early_bird', libelle: 'Tarif lancement' } }).mention_prix).toBe('25 CHF · Tarif lancement');
  });
  test('V607 WhatsApp : essai et événement payant enrichis ; Pass Duo inchangé', () => {
    const t = texteWhatsAppCampagne({ type: 'trial', share_url: 'https://a.ch/i/x', inviter_display: { prenom: 'Bassi' },
      date_label: 'mercredi 14 octobre', time_label: '18:45', lieu: 'Auvernier' });
    expect(t).toMatch(/Bassi t'invite à découvrir Afroboost/);
    expect(t).toMatch(/📅 Mercredi 14 octobre/);
    expect(t).toMatch(/Ton premier cours est offert/);
    expect(t).toMatch(/https:\/\/a\.ch\/i\/x/);
    const p = texteWhatsAppCampagne({ type: 'event_paid', title: 'Gala', share_url: 'L', inviter_display: { prenom: 'Bassi' },
      prix_actif: { prix: 25, palier: 'early_bird', libelle: 'Tarif lancement', prochain: { prix: 35 } } });
    // V610 : accroche personnalisée par le système, puis l'événement.
    expect(p).toMatch(/^Bassi t'invite à Afroboost 🔥🎧/);
    expect(p).toMatch(/Viens vivre Gala !/);
    expect(p).toMatch(/Tarif actuel : 25 CHF \(Tarif lancement\)/);
    expect(p).toMatch(/Plus tu réserves tôt/);
    expect(texteWhatsAppCampagne({ type: 'pass_duo', message: 'Viens', share_url: 'L' })).toMatch(/Viens/);
  });
  test('V610 WhatsApp Afroboost Silent : prénom de l\'invitant, date, heure, lieu, prix ACTIF, gratuité membres, lien perso', () => {
    const dto = { type: 'event_paid', title: 'AFROBOOST SILENT — ÉDITION SPÉCIALE',
      subtitle: '1 heure de cardio-danse afro au casque, accessible à tous les niveaux.',
      date_label: 'mercredi 28 octobre', time_label: '18:45', lieu: 'Chem. des Valangines 97, 2000 Neuchâtel',
      share_url: 'https://afroboost.com/i/JetonSophie', inviter_display: { prenom: 'Sophie' }, gratuit_membres: true,
      prix_actif: { prix: 30, palier: 'standard', libelle: 'Standard', prochain: { prix: 40 } } };
    const t = texteWhatsAppCampagne(dto);
    expect(t.split('\n')[0]).toBe("Sophie t'invite à Afroboost 🔥🎧");
    expect(t).toMatch(/Viens vivre AFROBOOST SILENT — ÉDITION SPÉCIALE :\n1 heure de cardio-danse afro au casque/);
    expect(t).toMatch(/📅 Mercredi 28 octobre\n⏰ 18:45\n📍 Chem\. des Valangines 97, 2000 Neuchâtel/);
    expect(t).toMatch(/🎟️ Tarif actuel : 30 CHF \(Standard\)/);
    expect(t).toMatch(/💜 Gratuit si tu as un abonnement Afroboost 8 mois actif\./);
    expect(t).toMatch(/Plus tu réserves tôt, moins c’est cher\./);
    expect(t).toMatch(/Réserve ta place 👇\nhttps:\/\/afroboost\.com\/i\/JetonSophie$/);
    expect(t).not.toMatch(/50 places|places maximum|envoyé/i);
    // Dernière minute : plus de palier suivant -> plus de « moins cher » ; sans liste membres -> pas de ligne gratuite.
    const d = texteWhatsAppCampagne({ ...dto, gratuit_membres: false, prix_actif: { prix: 40, palier: 'last_minute', libelle: 'Dernière minute', prochain: null } });
    expect(d).toMatch(/Tarif actuel : 40 CHF \(Dernière minute\)/);
    expect(d).not.toMatch(/moins c’est cher|Gratuit si/);
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
  test('partageable : actif + lien (V607 : événement payant aussi)', () => {
    expect(partageable({ status: 'active', share_url: 'u', type: 'trial' })).toBe(true);
    expect(partageable({ status: 'draft', share_url: 'u', type: 'trial' })).toBe(false);
    expect(partageable({ status: 'active', share_url: 'u', type: 'event_paid' })).toBe(true);
  });
  test('401/403 → reconnexion ; 409 activation : plus de message « fuseau » (V607)', () => {
    expect(messageErreur({ response: { status: 401 } })).toBe(TEXTE_RECONNEXION);
    expect(messageErreur({ response: { status: 403 } })).toBe(TEXTE_RECONNEXION);
    expect(messageErreur({ response: { status: 409 } }, 'activation')).not.toBe(TEXTE_FUSEAU_PALIERS);
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

/**
 * LOT A — L'ESPACE ABONNE N'AFFICHE JAMAIS UN SOLDE QU'IL NE PEUT PAS JUSTIFIER.
 *
 * Banc DOM reel : le composant est monte dans jsdom et on regarde CE QUI EST
 * RENDU. Une lecture de source ne prouverait pas qu'aucun chiffre ne subsiste
 * a l'ecran — c'est pourtant toute la promesse du lot.
 *
 * Trois garanties, une par bloc ci-dessous :
 *   1. cas OK      -> le solde affiche est celui de `discount_codes` ;
 *   2. cas AMBIGU  -> la phrase, et AUCUN chiffre (ni 0, ni somme, ni jauge) ;
 *   3. la reservation ne regresse pas : le bouton reste offert en AMBIGU, et
 *      `remaining_sessions` — la valeur que lit le serveur — reste intouchee.
 *
 * Aucun reseau : `axios` est un mouchard.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import SubscriberSpace from '../SubscriberSpace';

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('axios', () => ({
  __esModule: true,
  default: {
    get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn(),
    interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } },
  },
}));
jest.mock('../ConditionsParticipation', () => () => null);
jest.mock('../ConversionApresEssai', () => () => null);
jest.mock('../SubscriberOnboarding', () => () => null);
jest.mock('../SubscriberCockpit', () => () => null);
jest.mock('../SvgIcon', () => () => null);
jest.mock('../InvitationTemoignage', () => ({
  __esModule: true, default: () => null, enRepos: () => false
}));
jest.mock('../Publications', () => ({ PublishModal: () => null }));
jest.mock('qrcode.react', () => ({ QRCodeSVG: () => null }));
jest.mock('../ui/dialog', () => ({
  Dialog: ({ children }) => children,
  DialogContent: ({ children }) => children,
  DialogTitle: ({ children }) => children,
}));

const CODE = 'AFR-53F288';
const DEMAIN = new Date(Date.now() + 36 * 3600 * 1000).toISOString();

function espace(droits, legacy) {
  return {
    subscriber: { name: 'Ana Dupont', code: CODE, whatsapp: '+41760000000' },
    subscription: Object.assign(
      { id: 'sub-1', code: CODE, offer_name: 'PULSE x10 cours' }, legacy, droits),
    coach: { name: 'Afroboost' },
    upcoming_courses: [{ course_id: 'c-42', name: 'Afroboost Pulse', datetime: DEMAIN,
                        date: DEMAIN.slice(0, 10), time: '18:30' }],
    reservations: [],
  };
}

let conteneur;

async function monter(reponse) {
  axios.get.mockResolvedValue({ data: reponse });
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  await act(async () => {
    createRoot(conteneur).render(<SubscriberSpace accessCode={CODE} />);
  });
}

const bloc = () => conteneur.querySelector('[data-testid="subscriber-space-sessions"]');
const texteBloc = () => (bloc() ? bloc().textContent : '');

beforeEach(() => {
  window.posthog = { capture: jest.fn() };
  window.history.replaceState({}, '', `/espace/${CODE}`);
  jest.clearAllMocks();
  // LOT B3-S1.2 : l'espace exige desormais un jeton d'identite (OTP e-mail).
  // Ce banc-ci ne teste PAS l'authentification : on lui fournit donc un jeton
  // de banc valide pour qu'il atteigne l'ecran qu'il mesure. MONTAGE seul —
  // aucune assertion metier n'est touchee, et la garde de production reste
  // entiere : c'est bien elle qui lit ce jeton.
  window.localStorage.setItem('afroboost_espace_token', JSON.stringify({
    token: 'jeton-de-banc', code: CODE, slug: '',
    expires_at: new Date(Date.now() + 30 * 86400000).toISOString(),
  }));
});
afterEach(() => {
  if (conteneur) document.body.removeChild(conteneur);
  conteneur = null;
});

describe('LOT A — cas OK : la page Code promo fait foi', () => {
  test('affiche le solde canonique, pas celui de subscriptions', async () => {
    // La decision de reference du 27/08/2026 : AFR-53F288, total 9, used 8,
    // restant 1. `subscriptions` dit autre chose (7/2) : il ne doit PAS gagner.
    await monter(espace(
      { droits_etat: 'OK', droits_total: 9, droits_utilise: 8, droits_restant: 1 },
      { total_sessions: 9, used_sessions: 7, remaining_sessions: 2 }));
    expect(texteBloc()).toContain('1');
    expect(texteBloc()).toContain('/ 9');
    // Le 2 de `subscriptions` n'apparait nulle part dans le compteur.
    expect(bloc().querySelector('.text-3xl').textContent.replace(/\s/g, ''))
      .toBe('1/9');
  });

  test('un code partage garde son compteur (CLUBPMI)', async () => {
    await monter(espace(
      { droits_etat: 'OK', droits_total: 40, droits_utilise: 16, droits_restant: 24 },
      { total_sessions: 40, used_sessions: 16, remaining_sessions: 24 }));
    expect(bloc().querySelector('.text-3xl').textContent.replace(/\s/g, ''))
      .toBe('24/40');
    expect(conteneur.querySelector('[data-testid="droits-ambigus"]')).toBeNull();
  });
});

describe('LOT A — cas AMBIGU : aucun chiffre invente', () => {
  const ambigu = () => espace(
    { droits_etat: 'AMBIGU', droits_motif: 'plusieurs_abonnements',
      droits_total: null, droits_utilise: null, droits_restant: null,
      droits_message: 'Plusieurs forfaits sont enregistrés à ton nom — le coach vérifie ton solde.' },
    { total_sessions: 10, used_sessions: 8, remaining_sessions: 2 });

  test('affiche la phrase validee', async () => {
    await monter(ambigu());
    expect(conteneur.querySelector('[data-testid="droits-ambigus"]')).not.toBeNull();
    expect(texteBloc()).toContain('Plusieurs forfaits sont enregistrés à ton nom');
  });

  test('aucun solde : ni 0, ni la somme, ni la valeur de subscriptions', async () => {
    await monter(ambigu());
    // Le gros compteur n'existe plus du tout.
    expect(bloc().querySelector('.text-3xl')).toBeNull();
    // Et aucun chiffre ne subsiste dans le bloc — hors la phrase et le NOM du
    // forfait, qui contient un « 10 » sans etre un solde (« PULSE x10 cours »).
    const chiffres = texteBloc()
      .replace('Plusieurs forfaits sont enregistrés à ton nom — le coach vérifie ton solde.', '')
      .replace('PULSE x10 cours', '')
      .match(/\d+/g);
    expect(chiffres).toBeNull();
  });

  test('pas de jauge : une barre a une longueur, et toute longueur serait un chiffre', async () => {
    await monter(ambigu());
    expect(bloc().querySelector('.bg-white\\/10')).toBeNull();
  });

  test('le nom du forfait reste affiche', async () => {
    await monter(ambigu());
    expect(texteBloc()).toContain('PULSE x10 cours');
  });
});

describe('LOT A — la reservation ne regresse pas', () => {
  test('le bouton reste offert quand le solde est ambigu', async () => {
    await monter(espace(
      { droits_etat: 'AMBIGU', droits_motif: 'multi_codes', droits_restant: null,
        droits_total: null, droits_utilise: null,
        droits_message: 'Plusieurs forfaits sont enregistrés à ton nom — le coach vérifie ton solde.' },
      { total_sessions: 10, used_sessions: 8, remaining_sessions: 2 }));
    expect(texteBloc()).toContain('Réserver une séance');
  });

  test("sans champ LOT A, l'ecran est celui d'avant le lot", async () => {
    // Drapeau eteint, ou serveur plus ancien : aucun `droits_*` dans la reponse.
    await monter(espace({}, { total_sessions: 10, used_sessions: 8, remaining_sessions: 2 }));
    expect(bloc().querySelector('.text-3xl').textContent.replace(/\s/g, ''))
      .toBe('2/10');
    expect(conteneur.querySelector('[data-testid="droits-ambigus"]')).toBeNull();
  });

  test('etat INDISPONIBLE : repli sur l affichage historique', async () => {
    await monter(espace(
      { droits_etat: 'INDISPONIBLE', droits_restant: null, droits_total: null },
      { total_sessions: 10, used_sessions: 8, remaining_sessions: 2 }));
    expect(bloc().querySelector('.text-3xl').textContent.replace(/\s/g, ''))
      .toBe('2/10');
  });
});

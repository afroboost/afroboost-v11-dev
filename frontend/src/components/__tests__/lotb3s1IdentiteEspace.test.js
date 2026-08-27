/**
 * LOT B3-S1.2 — L'ESPACE NE S'OUVRE QU'APRES UNE PREUVE D'IDENTITE.
 *
 * CE QUE CE BANC PROUVE, ET C'EST LE POINT CENTRAL : sans jeton d'espace,
 * `GET /subscriber/space/{code}` n'est MEME PAS APPELE. L'ecran
 * d'identification n'est pas un rideau devant des donnees deja recuperees —
 * les donnees privees ne sont jamais demandees.
 *
 * POURQUOI. La route sert e-mail, telephone, objectifs, solde, reservations et
 * — pour un groupe — la liste des membres, a qui connait le code. Or 37 des 63
 * codes en base sont des libelles lisibles du type prenom + annee. Le jeton
 * V296 ne pouvait pas servir de preuve : `POST /subscriber/token` n'exige que
 * le code. Celui-ci s'obtient par un code a 6 chiffres envoye a l'adresse
 * ENREGISTREE en base.
 *
 * Aucun reseau, aucun e-mail : `axios` est un mouchard.
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
  __esModule: true, default: () => null, enRepos: () => false,
}));
jest.mock('../Publications', () => ({ PublishModal: () => null }));
jest.mock('qrcode.react', () => ({ QRCodeSVG: () => null }));
jest.mock('../ui/dialog', () => ({
  Dialog: ({ children }) => children,
  DialogContent: ({ children }) => children,
  DialogTitle: ({ children }) => children,
}));

const CODE = 'SYNTHCODE-1';
const CLE = 'afroboost_espace_token';
const MAIL = 'membre@exemple.invalid';

const espaceComplet = {
  subscriber: { name: 'Ana', code: CODE, whatsapp: '+41760000000' },
  subscription: { id: 's1', code: CODE, offer_name: 'PULSE', total_sessions: 10,
                  used_sessions: 6, remaining_sessions: 4 },
  coach: { name: 'Afroboost' }, upcoming_courses: [], reservations: [],
};

let conteneur;

async function monter(code = CODE) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  await act(async () => {
    createRoot(conteneur).render(<SubscriberSpace accessCode={code} />);
  });
}

const parId = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const saisir = async (id, valeur) => {
  const el = parId(id);
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value').set;
    setter.call(el, valeur);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
};
const cliquer = async (id) => {
  await act(async () => { parId(id).dispatchEvent(new MouseEvent('click', { bubbles: true })); });
};
const appelsEspace = () => axios.get.mock.calls.filter(
  (c) => String(c[0]).includes('/subscriber/space/'));

beforeEach(() => {
  jest.clearAllMocks();
  window.localStorage.clear();
  window.posthog = { capture: jest.fn() };
  window.history.replaceState({}, '', `/espace/${CODE}`);
  axios.get.mockResolvedValue({ data: espaceComplet });
});
afterEach(() => {
  if (conteneur) document.body.removeChild(conteneur);
  conteneur = null;
});

describe("Sans jeton : l'espace prive n'est meme pas demande", () => {
  test("l'ecran d'identification s'affiche", async () => {
    await monter();
    expect(parId('espace-identification')).not.toBeNull();
    expect(parId('espace-email')).not.toBeNull();
  });

  test("AUCUN appel a /subscriber/space n'est emis", async () => {
    await monter();
    expect(appelsEspace()).toHaveLength(0);
  });

  test("aucune donnee privee n'apparait a l'ecran", async () => {
    await monter();
    const t = conteneur.textContent;
    expect(t).not.toContain('PULSE');
    expect(t).not.toContain('+41760000000');
    expect(t).not.toContain('Ana');
  });

  test("un jeton d'un AUTRE code n'ouvre pas cet espace", async () => {
    window.localStorage.setItem(CLE, JSON.stringify({
      token: 'jeton-autre', code: 'AUTRE-CODE', slug: '',
      expires_at: new Date(Date.now() + 8.64e7).toISOString() }));
    await monter();
    expect(parId('espace-identification')).not.toBeNull();
    expect(appelsEspace()).toHaveLength(0);
  });

  test("un jeton EXPIRE renvoie a l'identification", async () => {
    window.localStorage.setItem(CLE, JSON.stringify({
      token: 'jeton-perime', code: CODE, slug: '',
      expires_at: new Date(Date.now() - 1000).toISOString() }));
    await monter();
    expect(parId('espace-identification')).not.toBeNull();
    expect(appelsEspace()).toHaveLength(0);
  });
});

describe("Le parcours OTP", () => {
  test("demande du code puis validation : le jeton est stocke et l'espace charge", async () => {
    axios.post.mockResolvedValueOnce({ data: { success: true, message: 'Si ces informations correspondent…' } });
    await monter();
    await saisir('espace-email', MAIL);
    await cliquer('espace-valider');
    expect(parId('espace-otp')).not.toBeNull();
    expect(parId('espace-info').textContent).toContain('Si ces informations correspondent');
    expect(appelsEspace()).toHaveLength(0);          // toujours rien de prive

    axios.post.mockResolvedValueOnce({ data: {
      success: true, token: 'JETON-ESPACE',
      expires_at: new Date(Date.now() + 30 * 8.64e7).toISOString() } });
    await saisir('espace-otp', '123456');
    await cliquer('espace-valider');

    const stocke = JSON.parse(window.localStorage.getItem(CLE));
    expect(stocke.token).toBe('JETON-ESPACE');
    expect(stocke.code).toBe(CODE);
    expect(appelsEspace()).toHaveLength(1);          // et SEULEMENT maintenant
    expect(parId('espace-identification')).toBeNull();
  });

  test("le jeton V296 n'est jamais reutilise comme preuve", async () => {
    window.localStorage.setItem('afroboost_subscriber_token', 'JETON-V296');
    await monter();
    expect(parId('espace-identification')).not.toBeNull();
    expect(appelsEspace()).toHaveLength(0);
  });
});

describe("Les echecs ne laissent jamais une page morte", () => {
  async function allerAlOtp() {
    axios.post.mockResolvedValueOnce({ data: { success: true, message: 'ok' } });
    await monter();
    await saisir('espace-email', MAIL);
    await cliquer('espace-valider');
  }

  test('OTP faux ou expire -> message, aucun acces', async () => {
    await allerAlOtp();
    axios.post.mockRejectedValueOnce({ response: { status: 400, data: { detail: 'x' } } });
    await saisir('espace-otp', '000000');
    await cliquer('espace-valider');
    expect(parId('espace-erreur').textContent).toContain('Code invalide ou expiré');
    expect(window.localStorage.getItem(CLE)).toBeNull();
    expect(appelsEspace()).toHaveLength(0);
    expect(parId('espace-valider')).not.toBeNull();   // on peut reessayer
  });

  test('cinq essais epuises : meme reponse, aucun acces', async () => {
    await allerAlOtp();
    for (let i = 0; i < 5; i += 1) {
      axios.post.mockRejectedValueOnce({ response: { status: 400 } });
      await saisir('espace-otp', '111111');
      await cliquer('espace-valider');
    }
    expect(parId('espace-erreur')).not.toBeNull();
    expect(window.localStorage.getItem(CLE)).toBeNull();
    expect(appelsEspace()).toHaveLength(0);
  });

  test('erreur reseau -> message et reessai possible, pas de page morte', async () => {
    await monter();
    axios.post.mockRejectedValueOnce(new Error('Network Error'));
    await saisir('espace-email', MAIL);
    await cliquer('espace-valider');
    expect(parId('espace-erreur').textContent).toContain('Vérifie ta connexion');
    expect(parId('espace-valider')).not.toBeNull();
    expect(parId('espace-email')).not.toBeNull();     // l'adresse reste corrigeable
  });

  test('503 -> message dedie, aucun acces', async () => {
    await allerAlOtp();
    axios.post.mockRejectedValueOnce({ response: { status: 503 } });
    await saisir('espace-otp', '123456');
    await cliquer('espace-valider');
    expect(parId('espace-erreur').textContent).toContain('indisponible');
    expect(window.localStorage.getItem(CLE)).toBeNull();
  });

  test('429 -> message de limite, aucun acces', async () => {
    await monter();
    axios.post.mockRejectedValueOnce({ response: { status: 429 } });
    await saisir('espace-email', MAIL);
    await cliquer('espace-valider');
    expect(parId('espace-erreur').textContent).toContain('Trop de demandes');
  });

  test("le recours au coach est toujours propose", async () => {
    await monter();
    expect(conteneur.textContent).toContain('Contacte ton coach');
  });

  test("aucune donnee sensible dans les messages d'erreur", async () => {
    await allerAlOtp();
    axios.post.mockRejectedValueOnce({ response: { status: 400 } });
    await saisir('espace-otp', '654321');
    await cliquer('espace-valider');
    const t = parId('espace-erreur').textContent;
    expect(t).not.toContain(MAIL);
    expect(t).not.toContain('654321');
    expect(t).not.toContain(CODE);
  });
});

describe("Renvoi, slug et rafraichissement", () => {
  test('le renvoi est temporise', async () => {
    axios.post.mockResolvedValueOnce({ data: { success: true, message: 'ok' } });
    await monter();
    await saisir('espace-email', MAIL);
    await cliquer('espace-valider');
    const b = parId('espace-renvoyer');
    expect(b.disabled).toBe(true);
    expect(b.textContent).toContain('Renvoyer dans');
  });

  test('« Corriger mon e-mail » ramene a l\'etape adresse', async () => {
    axios.post.mockResolvedValueOnce({ data: { success: true, message: 'ok' } });
    await monter();
    await saisir('espace-email', MAIL);
    await cliquer('espace-valider');
    await cliquer('espace-corriger');
    expect(parId('espace-email')).not.toBeNull();
    expect(parId('espace-otp')).toBeNull();
  });

  test('?m=slug est transmis aux DEUX appels et au chargement', async () => {
    window.history.replaceState({}, '', `/espace/${CODE}?m=aaa`);
    axios.post.mockResolvedValueOnce({ data: { success: true, message: 'ok' } });
    await monter();
    await saisir('espace-email', MAIL);
    await cliquer('espace-valider');
    expect(axios.post.mock.calls[0][1].m).toBe('aaa');

    axios.post.mockResolvedValueOnce({ data: { success: true, token: 'T',
      expires_at: new Date(Date.now() + 8.64e7).toISOString() } });
    await saisir('espace-otp', '123456');
    await cliquer('espace-valider');
    expect(axios.post.mock.calls[1][1].m).toBe('aaa');
    expect(JSON.parse(window.localStorage.getItem(CLE)).slug).toBe('aaa');
    expect(String(appelsEspace()[0][0])).toContain('m=aaa');
  });

  test('rafraichissement avec jeton valide : aucun ecran, chargement direct', async () => {
    window.localStorage.setItem(CLE, JSON.stringify({
      token: 'JETON-VALIDE', code: CODE, slug: '',
      expires_at: new Date(Date.now() + 30 * 8.64e7).toISOString() }));
    await monter();
    expect(parId('espace-identification')).toBeNull();
    expect(appelsEspace()).toHaveLength(1);
  });

  test('un jeton pour un autre membre du meme code n\'ouvre pas cet espace', async () => {
    window.history.replaceState({}, '', `/espace/${CODE}?m=aaa`);
    window.localStorage.setItem(CLE, JSON.stringify({
      token: 'T', code: CODE, slug: 'bbb',
      expires_at: new Date(Date.now() + 8.64e7).toISOString() }));
    await monter();
    expect(parId('espace-identification')).not.toBeNull();
    expect(appelsEspace()).toHaveLength(0);
  });
});

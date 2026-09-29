/**
 * PAR-3 — ENTRÉE DE CAMPAGNE (/duo/c/<token>) : le lien partagé par un coach
 * crée UNE invitation racine pour ce visiteur, puis ouvre /duo/<share_token>.
 *
 * Ce fichier monte l'APPLICATION ENTIÈRE (App.js réel, réseau simulé) pour
 * prouver le routage : /duo/c/abc n'est JAMAIS lu comme /duo/<token « c »>.
 * Règle absolue CLAUDE.md « jamais de boucle d'appels » : UN SEUL POST, jamais
 * rejoué au re-rendu ; une entrée déjà connue ne fait AUCUNE requête.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';

jest.mock('axios', () => {
  const inst = {
    interceptors: { request: { use: () => 0 }, response: { use: () => 0 } },
    get: (url, cfg) => (global.__parGet ? global.__parGet(url, cfg) : Promise.resolve({ data: [] })),
    post: (url, corps, cfg) => {
      (global.__parJournal = global.__parJournal || []).push({ url, corps, cfg });
      return global.__parPost ? global.__parPost(url, corps, cfg) : Promise.resolve({ data: {} });
    },
    put: () => Promise.resolve({ data: {} }),
    delete: () => Promise.resolve({ data: {} }),
    patch: () => Promise.resolve({ data: {} }),
    defaults: { headers: { common: {} } },
    isAxiosError: () => false,
  };
  inst.create = () => inst;
  return { __esModule: true, default: inst, ...inst };
});
jest.mock('@/App.css', () => ({}), { virtual: true });
jest.mock('@/lib/utils', () => jest.requireActual('../../../lib/utils'), { virtual: true });
jest.mock('../../SubscriberSpace', () => () => null);
jest.mock('../../CoachLoginModal', () => () => null);
jest.mock('../../ChatWidget', () => ({ ChatWidget: () => null }));
jest.mock('../../SuperAdminPanel', () => () => null);
jest.mock('../../CoachDashboard', () => ({ CoachDashboard: () => null }));
jest.mock('qrcode.react', () => {
  const R2 = jest.requireActual('react');
  return {
    QRCodeSVG: (p) => R2.createElement('svg', { 'data-testid': 'qr-svg', 'data-value': p.value }),
    QRCodeCanvas: () => null,
  };
});

const App = require('../../../App').default;
const EntreeCampagne = require('../EntreeCampagne').default;
const InvitationDuo = require('../InvitationDuo').default;
const PC = require('../../../utils/parrainageCampagne');

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

let conteneur = null;
let racine = null;
let redirections = [];

beforeAll(() => {
  window.matchMedia = (q) => ({ matches: false, media: q, onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent() { return false; } });
  global.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } };
  window.scrollTo = () => {};
  Element.prototype.scrollTo = function () {};
  Element.prototype.scrollIntoView = function () {};
});

beforeEach(() => {
  jest.spyOn(console, 'log').mockImplementation(() => {});
  jest.spyOn(console, 'warn').mockImplementation(() => {});
  jest.spyOn(console, 'error').mockImplementation(() => {});
  localStorage.clear();
  sessionStorage.clear();
  global.__parJournal = [];
  global.__parGet = null;
  global.__parPost = null;
  redirections = [];
  PC._resetEntreesPourTest();
  PC.navigation.remplacer = (url) => { redirections.push(url); };
});

afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
  jest.restoreAllMocks();
  window.history.replaceState({}, '', '/');
  localStorage.clear();
});

const par = (id) => document.querySelector(`[data-testid="${id}"]`);
const postsEntree = () => (global.__parJournal || []).filter((j) => /\/referral\/campaign\/[^/]+\/entry$/.test(j.url));

async function vider() {
  for (let i = 0; i < 8; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await act(async () => { await Promise.resolve(); });
  }
}

async function monter(element) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(element); });
  await vider();
}

async function monterApp(url) {
  window.history.replaceState({}, '', url);
  await monter(React.createElement(App));
}

const refus = (status, extra) => () => Promise.reject(Object.assign({ response: Object.assign({ status, headers: {}, data: {} }, extra || {}) }));

describe('routage App', () => {
  test('/duo/c/abc monte EntreeCampagne (pas InvitationDuo avec le jeton « c »)', async () => {
    global.__parPost = () => new Promise(() => {}); // reste en attente : on observe l'écran d'attente
    await monterApp('/duo/c/abc');
    expect(par('entree-campagne')).not.toBeNull();
    expect(par('invitation-duo')).toBeNull();
    expect(postsEntree()).toHaveLength(1);
    expect(postsEntree()[0].url).toMatch(/\/api\/referral\/campaign\/abc\/entry$/);
  });

  test('/duo/c/abc/ (barre finale) : même page', async () => {
    global.__parPost = () => new Promise(() => {});
    await monterApp('/duo/c/abc/');
    expect(par('entree-campagne')).not.toBeNull();
  });

  test('non-régression : /duo/<token> classique reste InvitationDuo, aucun POST d\'entrée', async () => {
    global.__parGet = () => new Promise(() => {});
    await monterApp('/duo/TOK123');
    expect(par('invitation-duo')).not.toBeNull();
    expect(par('entree-campagne')).toBeNull();
    expect(postsEntree()).toHaveLength(0);
  });
});

describe('EntreeCampagne — un seul appel, puis la page de l\'invitation', () => {
  test('201 : UN SEUL POST, stockage {share_token, entry_key}, location.replace(/duo/<t>)', async () => {
    global.__parPost = () => Promise.resolve({ status: 201, data: { share_token: 'P0TOK', entry_key: 'CLE-1', target: '/duo/P0TOK' } });
    await monterApp('/duo/c/abc');
    expect(postsEntree()).toHaveLength(1);
    expect(redirections).toEqual(['/duo/P0TOK']);
    expect(JSON.parse(localStorage.getItem('afroboost_campagne_abc'))).toEqual({ share_token: 'P0TOK', entry_key: 'CLE-1' });
    // Pas de X-Entry-Key au premier passage.
    const h = (postsEntree()[0].cfg && postsEntree()[0].cfg.headers) || {};
    expect(h['X-Entry-Key']).toBeUndefined();
  });

  test('re-rendu : pas de second POST', async () => {
    global.__parPost = () => new Promise(() => {});
    await monter(<EntreeCampagne token="abc" />);
    await act(async () => { racine.render(<EntreeCampagne token="abc" />); });
    await act(async () => { racine.render(<EntreeCampagne token="abc" />); });
    await vider();
    expect(postsEntree()).toHaveLength(1);
  });

  test('entrée déjà connue (localStorage) : AUCUNE requête, redirection directe', async () => {
    localStorage.setItem('afroboost_campagne_abc', JSON.stringify({ share_token: 'DEJA', entry_key: 'K' }));
    await monterApp('/duo/c/abc');
    expect(postsEntree()).toHaveLength(0);
    expect(redirections).toEqual(['/duo/DEJA']);
  });

  test('X-Entry-Key envoyée si connue (sans share_token) ; 200 garde la clé existante', async () => {
    localStorage.setItem('afroboost_campagne_abc', JSON.stringify({ entry_key: 'CLE-CONNUE' }));
    global.__parPost = () => Promise.resolve({ status: 200, data: { share_token: 'P0B', target: '/duo/P0B' } });
    await monter(<EntreeCampagne token="abc" />);
    expect(postsEntree()).toHaveLength(1);
    expect(postsEntree()[0].cfg.headers['X-Entry-Key']).toBe('CLE-CONNUE');
    expect(redirections).toEqual(['/duo/P0B']);
    expect(JSON.parse(localStorage.getItem('afroboost_campagne_abc'))).toEqual({ share_token: 'P0B', entry_key: 'CLE-CONNUE' });
  });

  test('attribution existante (dont ?ref=) transmise dans le corps', async () => {
    global.__parPost = () => new Promise(() => {});
    await monterApp('/duo/c/abc?ref=studio-lac');
    const corps = postsEntree()[0].corps || {};
    expect(corps.attribution).toBeTruthy();
    expect(corps.attribution.last.source).toBe('partenaire');
    expect(corps.attribution.last.content).toBe('studio-lac');
  });

  test('cible serveur hors /duo/ : ignorée, la page reconstruit /duo/<share_token>', async () => {
    global.__parPost = () => Promise.resolve({ status: 201, data: { share_token: 'P0C', entry_key: 'K', target: 'https://evil.example/duo/x' } });
    await monter(<EntreeCampagne token="abc" />);
    expect(redirections).toEqual(['/duo/P0C']);
  });
});

describe('EntreeCampagne — messages clairs', () => {
  test.each([
    [404, {}, "Cette invitation n'est plus disponible."],
    [404, { data: { detail: 'parrainage_chaine_desactive' } }, "Cette invitation n'est plus disponible."],
    [410, {}, 'La séance de cette invitation est passée.'],
    [409, { headers: { 'x-refus-raison': 'campagne_complete' } }, 'Cette invitation a atteint son nombre maximal de places.'],
    [429, {}, 'Trop de tentatives, réessaie dans un instant.'],
  ])('%i → message', async (status, extra, texte) => {
    global.__parPost = refus(status, extra);
    await monter(<EntreeCampagne token="abc" />);
    expect(par('entree-campagne-message').textContent).toContain(texte);
    expect(redirections).toEqual([]);
    expect(postsEntree()).toHaveLength(1);
    expect(localStorage.getItem('afroboost_campagne_abc')).toBeNull();
  });

  test('404 : lien vers l\'accueil', async () => {
    global.__parPost = refus(404);
    await monter(<EntreeCampagne token="abc" />);
    expect(par('entree-campagne-accueil').getAttribute('href')).toBe('/');
  });

  test('erreur réseau → bouton Réessayer (geste), jamais de nouvel appel tout seul', async () => {
    global.__parPost = () => Promise.reject(new Error('Network Error'));
    await monter(<EntreeCampagne token="abc" />);
    expect(par('entree-campagne-reessayer')).not.toBeNull();
    await vider();
    expect(postsEntree()).toHaveLength(1);
    global.__parPost = () => Promise.resolve({ status: 201, data: { share_token: 'P0R', entry_key: 'K2', target: '/duo/P0R' } });
    await act(async () => { par('entree-campagne-reessayer').click(); });
    await vider();
    expect(postsEntree()).toHaveLength(2);
    expect(redirections).toEqual(['/duo/P0R']);
  });
});

describe('InvitationDuo — pass racine de campagne : un seul billet', () => {
  const COURSE = { id: 'c1', name: 'Afroboost Dimanche', time: '18:30', locationName: 'Lac' };
  const PUB = { status: 'waiting', course: COURSE, occurrence: '2026-10-04T18:30:00', expired: false,
    inviter_display: { prenom: 'Coach Bassi', source: 'coach' } };
  const INVITE = { role: 'invitee', first_name: 'Aminata', reservationCode: 'AF7D1A', qr_value: 'https://afroboost.com/validate/AF7D1A?res=2' };
  const SPONSOR = { role: 'sponsor', first_name: 'Bassi', reservationCode: 'AF3B9C', qr_value: 'https://afroboost.com/validate/AF3B9C?res=1' };

  async function rejoindre(tickets) {
    global.__parGet = () => Promise.resolve({ data: PUB });
    await monter(<InvitationDuo token="P0TOK" />);
    const saisir = (id, v) => act(async () => {
      const el = par(id);
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(el, v);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await saisir('invitation-prenom', 'Aminata');
    await saisir('invitation-email', 'aminata@example.com');
    await saisir('invitation-whatsapp', '+41 79 000 00 00');
    await act(async () => { par('invitation-consent').click(); });
    global.__parPost = () => Promise.resolve({ data: { status: 'unlocked', tickets, blocked_reason: null } });
    await act(async () => { par('invitation-rejoindre').click(); });
    await vider();
  }

  test('billet de l\'invité seul : un QR, texte « ton billet », pas « chacun votre billet »', async () => {
    await rejoindre([INVITE]);
    const succes = par('invitation-succes');
    expect(succes).not.toBeNull();
    expect(document.querySelectorAll('[data-testid="qr-svg"]')).toHaveLength(1);
    expect(par('billet-invitee')).not.toBeNull();
    expect(par('billet-sponsor')).toBeNull();
    expect(succes.textContent).not.toContain('chacun votre billet');
    expect(succes.textContent).toContain('Ton billet');
  });

  test('pass ordinaire (deux billets) : texte inchangé', async () => {
    await rejoindre([SPONSOR, INVITE]);
    expect(par('invitation-succes').textContent).toContain('Vous avez chacun votre billet pour la même séance.');
    expect(par('invitation-succes').textContent).toContain('débloqué');
    expect(document.querySelectorAll('[data-testid="qr-svg"]')).toHaveLength(2);
  });
});

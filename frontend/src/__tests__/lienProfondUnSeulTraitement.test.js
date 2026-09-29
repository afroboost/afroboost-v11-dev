/**
 * DL-1 — LE LIEN PROFOND `?offre=<id>&reserver=1` EST TRAITÉ PAR UN SEUL COMPOSANT.
 *
 * LE DÉFAUT (préexistant depuis V542, bab6835b)
 * ===========================================================================
 * Quand le carrousel historique est rendu (`aimantsActifs` faux : catalogue sans
 * offre « aimant », OU visiteur connecté — abonné, coach, admin), DEUX composants
 * lisaient le même lien :
 *   1. `OffresAimants` monté en CONTRÔLEUR (`cartes={false}`) appelait
 *      `onChoisir(o)` = `handleSelectOffer` → formulaire OUVERT ;
 *   2. la sonde V371/V449 d'`OffersSliderAutoPlay` retrouvait la carte et
 *      rappelait `onSelectOffer` sur la MÊME offre → la bascule v56 de
 *      `handleSelectOffer` (« même offre déjà sélectionnée → on la désélectionne »)
 *      REFERMAIT le formulaire. Mesuré ici : ouvert à 100 ms, fermé à 200 ms.
 *
 * CE FICHIER MONTE L'APPLICATION ENTIÈRE (App.js réel, réseau simulé) : c'est la
 * seule façon d'observer la course entre les deux effets telle qu'elle a lieu.
 * Seuls les écrans lourds hors sujet (chat, tableau de bord, espace abonné) sont
 * remplacés par des bouchons.
 */
// React, react-dom et App sont rechargés ENSEMBLE à chaque cas
// (`jest.isolateModules`) : App.js garde des caches au niveau du module, et un
// cas ne doit jamais hériter des offres du précédent.
let R = null;
let act = null;

jest.mock('axios', () => {
  const inst = {
    interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } },
    get: jest.fn((url, cfg) => (global.__dl1Get ? global.__dl1Get(url, cfg) : Promise.resolve({ data: [] }))),
    post: jest.fn(() => Promise.resolve({ data: {} })),
    put: jest.fn(() => Promise.resolve({ data: {} })),
    delete: jest.fn(() => Promise.resolve({ data: {} })),
    patch: jest.fn(() => Promise.resolve({ data: {} })),
    defaults: { headers: { common: {} } },
    create: jest.fn(),
    isAxiosError: () => false,
  };
  inst.create.mockImplementation(() => inst);
  return { __esModule: true, default: inst, ...inst };
});
jest.mock('@/App.css', () => ({}), { virtual: true });
jest.mock('@/lib/utils', () => jest.requireActual('../lib/utils'), { virtual: true });
jest.mock('../components/SubscriberSpace', () => () => { const R2 = jest.requireActual('react'); return R2.createElement('div', { 'data-testid': 'bouchon-espace' }); });
jest.mock('../components/CoachLoginModal', () => () => { const R2 = jest.requireActual('react'); return R2.createElement('div', { 'data-testid': 'bouchon-login' }); });
jest.mock('../components/ChatWidget', () => ({ ChatWidget: () => null }));
jest.mock('../components/SuperAdminPanel', () => () => { const R2 = jest.requireActual('react'); return R2.createElement('div', { 'data-testid': 'bouchon-superadmin' }); });
// Le tableau de bord réel est hors sujet : un bouchon repérable suffit — chaque
// cas vérifie qu'on est bien sur la VITRINE, pas sur le tableau de bord.
jest.mock('../components/CoachDashboard', () => {
  const R2 = jest.requireActual('react');
  return { CoachDashboard: () => R2.createElement('div', { 'data-testid': 'bouchon-dashboard' }) };
});

global.IS_REACT_ACT_ENVIRONMENT = true;

const ESSAI = { id: 'o-essai', name: "Cours d'essai", price: 0, offer_type: 'single_class', pack_sessions: 1, visible: true, position: 1 };
const ESSAI_BIS = { id: 'o-decouverte', name: 'Séance découverte', price: 0, offer_type: 'single_class', pack_sessions: 1, visible: true, position: 2 };
const MENSUEL = { id: 'o-men', name: 'Mensuel Liberté', price: 89, offer_type: 'subscription', pack_sessions: 8, billing_mode: 'mensuel_auto', visible: true, position: 3 };
const CATALOGUES = {
  'AVEC aimants': [ESSAI, MENSUEL],
  'SANS aimants': [ESSAI, ESSAI_BIS],
};

// Jeton de forme valide (non signé : le serveur est simulé), expiration en 2100.
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64').replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
const JETON_ADMIN = `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64({ sub: 'contact.artboost@gmail.com', email: 'contact.artboost@gmail.com', role: 'super_admin', exp: 4102444800 })}.signature`;

// Chaque rôle = l'état réel du localStorage de ce profil.
const ROLES = {
  anonyme: () => {},
  abonne: () => { localStorage.setItem('afroboost_subscriber_token', 'jeton-abonne'); },
  // Coach revenu sur son site (« retour au site » retire afroboost_coach_mode).
  coach: () => { localStorage.setItem('afroboost_coach_user', JSON.stringify({ email: 'coach.partenaire@example.ch', name: 'Coach' })); },
  // Super-admin : session restaurée en MODE COACH (jeton + admin_persist). Le
  // lien d'offre le met en « Vue visiteur » (V546) au lieu du tableau de bord.
  admin: () => {
    localStorage.setItem('afroboost_jwt', JETON_ADMIN);
    localStorage.setItem('afroboost_admin_persist', JSON.stringify({ email: 'contact.artboost@gmail.com', name: 'Admin' }));
  },
};

let conteneur = null;
let racine = null;

beforeAll(() => {
  window.matchMedia = (q) => ({ matches: false, media: q, onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent() { return false; } });
  global.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } };
  window.scrollTo = () => {};
  Element.prototype.scrollTo = function () {};
  Element.prototype.scrollBy = function () {};
  Element.prototype.scrollIntoView = function () {};
});

beforeEach(() => {
  jest.useFakeTimers();
  jest.spyOn(console, 'log').mockImplementation(() => {});
  jest.spyOn(console, 'warn').mockImplementation(() => {});
  jest.spyOn(console, 'error').mockImplementation(() => {});
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
  document.body.innerHTML = '';
  jest.useRealTimers();
  jest.restoreAllMocks();
  window.history.replaceState({}, '', '/');
  localStorage.clear();
});

const formulaire = () => !!document.querySelector('[data-testid="user-info-section"]');

async function avancer(ms) {
  await act(async () => { jest.advanceTimersByTime(ms); });
  await act(async () => {});
}

/** Monte App.js sur `url`, catalogue `offres`, profil `role`, largeur `largeur`.
 *  Rend la trace du formulaire, échantillonnée toutes les 100 ms pendant 2 s. */
async function ouvrir({ url, offres, role, largeur }) {
  ROLES[role]();
  window.innerWidth = largeur;
  window.history.replaceState({}, '', url);
  global.__dl1Get = (u) => {
    if (/\/offers(\?|$)/.test(u)) return Promise.resolve({ data: offres });
    if (/\/courses(\?|$)/.test(u)) return Promise.resolve({ data: [] });
    if (/\/concept(\?|$)/.test(u)) return Promise.resolve({ data: {} });
    if (/\/auth\/role(\?|$)/.test(u)) return Promise.resolve({ data: { role: 'super_admin', is_coach: true, is_super_admin: true } });
    if (/\/auth\/me(\?|$)/.test(u)) return Promise.resolve({ data: { token: JETON_ADMIN } });
    return Promise.resolve({ data: [] });
  };
  let App; let createRoot;
  jest.isolateModules(() => {
    R = require('react');
    ({ createRoot } = require('react-dom/client'));
    App = require('../App').default;
  });
  act = R.act;
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(R.createElement(App)); });
  await act(async () => {});
  // On est sur la vitrine (ni tableau de bord, ni formulaire de connexion).
  expect(document.querySelector('[data-testid="bouchon-dashboard"]')).toBeNull();
  expect(document.querySelector('[data-testid="bouchon-login"]')).toBeNull();
  const trace = [];
  for (let i = 0; i < 20; i += 1) {
    await avancer(100);
    trace.push(formulaire() ? 1 : 0);
  }
  return trace.join('');
}

describe('DL-1 — `?offre=<id>&reserver=1` : le formulaire s’ouvre et RESTE ouvert', () => {
  const cas = [];
  Object.keys(ROLES).forEach((role) => {
    Object.keys(CATALOGUES).forEach((cat) => {
      [390, 1280].forEach((largeur) => cas.push([role, cat, largeur]));
    });
  });

  test.each(cas)('%s · catalogue %s · %i px', async (role, cat, largeur) => {
    const trace = await ouvrir({ url: '/?offre=o-essai&reserver=1', offres: CATALOGUES[cat], role, largeur });
    // Le formulaire s'est ouvert…
    expect(trace).toContain('1');
    // …et, une fois ouvert, ne s'est JAMAIS refermé (aucune désélection).
    expect(trace.slice(trace.indexOf('1'))).not.toContain('0');
    expect(formulaire()).toBe(true);
    // Le rendu attendu : les cartes aimants quand le parcours conversion est
    // actif ET que le catalogue a un aimant — anonyme, ou admin en session coach
    // (V546 : un lien d'offre ouvert en mode coach vaut « Vue visiteur ») ; le
    // carrousel historique pour tous les autres.
    const aimants = (role === 'anonyme' || role === 'admin') && cat === 'AVEC aimants';
    expect(!!document.querySelector('[data-testid="offres-aimants"]')).toBe(aimants);
    expect(!!document.querySelector('[data-testid="offers-slider"]')).toBe(!aimants);
  });
});

describe('DL-1 — ce qui ne doit PAS changer', () => {
  test.each([
    ['anonyme', 'SANS aimants'], ['abonne', 'AVEC aimants'], ['anonyme', 'AVEC aimants'],
  ])('V371 — lien SANS `reserver=1` (%s, %s) : jamais de formulaire', async (role, cat) => {
    const trace = await ouvrir({ url: '/?offre=o-essai', offres: CATALOGUES[cat], role, largeur: 390 });
    expect(trace).not.toContain('1');
  });

  test.each([['anonyme', 'SANS aimants'], ['abonne', 'AVEC aimants'], ['anonyme', 'AVEC aimants']])(
    'offre inconnue (%s, %s) : rien ne s’ouvre', async (role, cat) => {
      const trace = await ouvrir({ url: '/?offre=o-inexistante&reserver=1', offres: CATALOGUES[cat], role, largeur: 1280 });
      expect(trace).not.toContain('1');
    });

  test('clic manuel sur la carte déjà ouverte : elle se referme toujours (bascule v56 conservée)', async () => {
    await ouvrir({ url: '/?offre=o-essai&reserver=1', offres: CATALOGUES['SANS aimants'], role: 'abonne', largeur: 1280 });
    expect(formulaire()).toBe(true);
    const carte = document.querySelector('[data-testid="offer-card-o-essai"]');
    expect(carte).not.toBeNull();
    await act(async () => { carte.click(); });
    await avancer(300);
    expect(formulaire()).toBe(false);
    // Et un second clic la rouvre.
    await act(async () => { document.querySelector('[data-testid="offer-card-o-essai"]').click(); });
    await avancer(300);
    expect(formulaire()).toBe(true);
  });
});


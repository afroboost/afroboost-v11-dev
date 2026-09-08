/**
 * F3 FINAL — LE HANDOFF SPORDATEUR : NAVIGATION IMMÉDIATE, MOBILE COMPRIS.
 *
 * CE QUE ÇA PROUVE (§13)
 *   - jeton en cache -> `entrerDansSpordate` navigue DIRECTEMENT, sans POST ;
 *   - PAS de jeton -> navigation IMMÉDIATE vers la route serveur, sans attendre
 *     le moindre fetch (le tap ne bloque jamais) ;
 *   - `next` (/profile) est porté proprement dans les deux cas ;
 *   - `prechargerSpordate` ne tente RIEN sans identité (pas de 403 anonyme) et
 *     met bien le jeton en cache quand il y a une identité ;
 *   - `urlEntreeServeur` ne laisse passer qu'un `next` interne.
 *
 * axios est mocké ; `window.location.href` est capturé sans navigation réelle.
 */
import axios from 'axios';
import {
  prechargerSpordate, entrerDansSpordate, urlEntreeServeur, _resetHandoffPourTest,
} from '../spordateHandoff';

jest.mock('axios', () => ({
  __esModule: true,
  default: { post: jest.fn(), get: jest.fn() },
}));

let hrefs;
beforeEach(() => {
  jest.clearAllMocks();
  _resetHandoffPourTest();
  try { localStorage.clear(); } catch (e) {}
  hrefs = [];
  // Capturer les affectations de window.location.href sans naviguer.
  delete window.location;
  window.location = {};
  Object.defineProperty(window.location, 'href', {
    configurable: true,
    get() { return hrefs[hrefs.length - 1] || ''; },
    set(v) { hrefs.push(v); },
  });
});

const dernierHref = () => hrefs[hrefs.length - 1];

test('A. PAS de jeton en cache → navigation IMMÉDIATE vers la route serveur, sans POST', () => {
  entrerDansSpordate();                      // appel synchrone
  expect(dernierHref()).toContain('/api/spordate/enter');   // déjà navigué
  expect(axios.post).not.toHaveBeenCalled(); // aucun fetch attendu avant de partir
});

test('B. PAS de jeton + next=/profile → route serveur avec next encodé, immédiat', () => {
  entrerDansSpordate('/profile');
  expect(dernierHref()).toBe(`${urlEntreeServeur('/profile')}`);
  expect(dernierHref()).toContain('next=%2Fprofile');
  expect(axios.post).not.toHaveBeenCalled();
});

test('C. jeton pré-obtenu au montage → navigation DIRECTE vers /rencontre?t=…, sans POST au clic', async () => {
  localStorage.setItem('afroboost_jwt', 'x');
  axios.post.mockResolvedValue({ data: { url: '/rencontre?t=JETON' } });
  await prechargerSpordate();                // le montage a pré-obtenu le jeton
  expect(axios.post).toHaveBeenCalledTimes(1);

  axios.post.mockClear();
  entrerDansSpordate('/profile');            // clic : DIRECT, aucun nouveau POST
  expect(dernierHref()).toBe('/rencontre?t=JETON&next=%2Fprofile');
  expect(axios.post).not.toHaveBeenCalled();
});

test('D. prechargerSpordate SANS identité connue → aucun POST (pas de 403 anonyme)', async () => {
  // localStorage vide = visiteur anonyme
  await prechargerSpordate();
  expect(axios.post).not.toHaveBeenCalled();
});

test('E. prechargerSpordate est idempotent (un seul POST même appelé plusieurs fois)', async () => {
  localStorage.setItem('afroboost_subscriber_token', 'x');
  let resoudre;
  axios.post.mockReturnValue(new Promise((r) => { resoudre = r; }));
  prechargerSpordate(); prechargerSpordate(); prechargerSpordate();
  expect(axios.post).toHaveBeenCalledTimes(1);
  resoudre({ data: { url: '/rencontre?t=Z' } });
});

test('F. urlEntreeServeur : next interne encodé ; rien d’autre', () => {
  expect(urlEntreeServeur()).toContain('/api/spordate/enter');
  expect(urlEntreeServeur()).not.toContain('next=');
  expect(urlEntreeServeur('/profile/abc')).toContain('next=%2Fprofile%2Fabc');
  // un next non interne (ne commence pas par '/') est ignoré
  expect(urlEntreeServeur('https://evil.example')).not.toContain('next=');
  expect(urlEntreeServeur('mailto:x')).not.toContain('next=');
});

test('G. jeton en cache + next absent → /rencontre?t=… inchangé', async () => {
  localStorage.setItem('afroboost_identity', 'x');
  axios.post.mockResolvedValue({ data: { url: '/rencontre?t=K' } });
  await prechargerSpordate();
  entrerDansSpordate();
  expect(dernierHref()).toBe('/rencontre?t=K');
});

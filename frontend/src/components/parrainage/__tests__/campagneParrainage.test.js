/**
 * Invitation du coach → /parrainage?campagne=<token>.
 *
 * CE QU'IL PROUVE
 *   - avec `?campagne=abc`, le corps de POST /api/referral/pass porte
 *     `referral_campaign: 'abc'` ;
 *   - sans paramètre, le corps est STRICTEMENT celui d'avant (aucune clé en plus) ;
 *   - fonctions pures `lireCampagneUrl` / `avecCampagne`.
 * axios est mocké : aucun réseau.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import CentreParrainage from '../CentreParrainage';
import { lireCampagneUrl, avecCampagne, _resetParrainagePourTest } from '../../../utils/parrainage';

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), patch: jest.fn(), delete: jest.fn() },
}));
jest.mock('qrcode.react', () => ({
  QRCodeSVG: (p) => <svg data-testid="qr-svg" data-value={p.value} />,
  QRCodeCanvas: (p) => <canvas data-testid="qr-canvas" data-value={p.value} />,
}));
jest.mock('../../../utils/spordateHandoff', () => ({
  __esModule: true,
  prechargerSpordate: jest.fn(),
  entrerDansSpordate: jest.fn(),
}));

const COURSE = { id: 'c1', name: 'Afroboost Dimanche', time: '18:30', locationName: 'Bord du Lac' };
const OCC = '2030-10-06T18:30:00';
const CONFIG = { enabled: true, courses: [{ ...COURSE, weekday: 0, occurrences: [OCC] }] };
const ME = { enabled: true, sponsor: { first_name: 'Bassi' }, stats: {}, passes: [], invitations: [], history: [] };

let conteneur, racine;
beforeEach(() => {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  axios.get.mockReset(); axios.post.mockReset(); axios.put.mockReset(); axios.patch.mockReset();
  window.localStorage.clear();
  window.localStorage.setItem('afroboost_subscriber_token', 'dev-1');
  _resetParrainagePourTest();
  axios.get.mockImplementation((url) => {
    const u = String(url);
    if (u.endsWith('/referral/me')) return Promise.resolve({ data: ME });
    if (u.endsWith('/referral/config')) return Promise.resolve({ data: CONFIG });
    if (u.endsWith('/referral/invitation')) return Promise.resolve({ data: { identity: {}, default_message: '', pass: null } });
    if (u.endsWith('/spordate/unified-profile/me')) return Promise.resolve({ data: { lie: false } });
    return Promise.resolve({ data: {} });
  });
  axios.post.mockResolvedValue({ data: { id: 'p1', status: 'locked', course: COURSE, occurrence: OCC, share_url: 'https://afroboost.com/api/share/duo/T' } });
});
afterEach(() => {
  if (racine) act(() => racine.unmount());
  racine = null;
  conteneur.remove();
  window.history.pushState({}, '', '/');
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
async function flush() {
  await act(async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); });
}
async function monter() {
  await act(async () => { racine = createRoot(conteneur); racine.render(<CentreParrainage />); });
  await flush();
}
async function cliquer(id) {
  const el = par(id);
  if (!el) throw new Error(`élément absent : ${id}`);
  await act(async () => { el.click(); });
  await flush();
}
async function creerViaAssistant() {
  await monter();
  await cliquer('wizard-suivant');
  await cliquer('wizard-suivant');
  await cliquer('wizard-creer');
  const appel = axios.post.mock.calls.find((c) => /\/referral\/pass$/.test(String(c[0])));
  if (!appel) throw new Error('POST /referral/pass absent');
  return appel[1];
}

describe('fonctions pures', () => {
  test('lireCampagneUrl lit ?campagne= ; illisible ou absent → ""', () => {
    expect(lireCampagneUrl('?campagne=abc')).toBe('abc');
    expect(lireCampagneUrl('?course=c1')).toBe('');
    expect(lireCampagneUrl('?campagne=<script>')).toBe('');
  });
  test('avecCampagne : sans jeton, le même objet ; avec, referral_campaign ajouté', () => {
    const corps = { course_id: 'c1' };
    expect(avecCampagne(corps, '')).toBe(corps);
    expect(avecCampagne(corps, undefined)).toBe(corps);
    expect(avecCampagne(corps, 'abc')).toEqual({ course_id: 'c1', referral_campaign: 'abc' });
    expect(corps).toEqual({ course_id: 'c1' }); // jamais muté
  });
});

describe('CentreParrainage — ?campagne= transmis à la création du pass', () => {
  test('avec ?campagne=abc → referral_campaign: "abc"', async () => {
    window.history.pushState({}, '', '/parrainage?campagne=abc');
    const corps = await creerViaAssistant();
    expect(corps.referral_campaign).toBe('abc');
    expect(corps.course_id).toBe('c1');
  });
  test('sans paramètre → corps identique à avant (aucune clé referral_campaign)', async () => {
    window.history.pushState({}, '', '/parrainage');
    const corps = await creerViaAssistant();
    expect(corps).not.toHaveProperty('referral_campaign');
    expect(Object.keys(corps).sort()).toEqual(expect.arrayContaining(['course_id', 'occurrence', 'terms_accepted', 'invitation']));
  });
});

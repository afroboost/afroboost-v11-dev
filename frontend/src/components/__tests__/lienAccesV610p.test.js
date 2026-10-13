/**
 * V610p — e-mail d'accès -> ESPACE (jamais le ChatWidget), événement conservé, partage
 * contextuel. axios et fetch sont mockés : aucun réseau, aucune donnée réelle.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

jest.mock('axios', () => {
  const m = { get: jest.fn(), post: jest.fn(), put: jest.fn(), create: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } };
  m.create.mockReturnValue(m);
  return { __esModule: true, default: m, ...m };
});
jest.mock('@/lib/utils', () => ({ cn: (...a) => a.filter(Boolean).join(' ') }), { virtual: true });
// eslint-disable-next-line import/first
import axios from 'axios';
// eslint-disable-next-line import/first
import SubscriberSpace from '../SubscriberSpace';
// eslint-disable-next-line import/first
import AccesMembreEvenement from '../AccesMembreEvenement';
// eslint-disable-next-line import/first
import PartagerInviter from '../PartagerInviter';
// eslint-disable-next-line import/first
import InvitationPublique from '../InvitationPublique';
// eslint-disable-next-line import/first
import { lireIntentionMembre } from '../../utils/participationEvenement';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
jest.setTimeout(20000);
let conteneur = null; let racine = null;
function rendre(el) { conteneur = document.createElement('div'); document.body.appendChild(conteneur); racine = createRoot(conteneur); racine.render(el); }
afterEach(() => {
  if (racine) act(() => racine.unmount());
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
  delete global.fetch; window.localStorage.clear(); window.sessionStorage.clear();
  window.history.replaceState({}, '', '/');
  jest.clearAllMocks();
});
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
async function attendre(fn) { let e; for (let i = 0; i < 200; i += 1) { try { fn(); return; } catch (x) { e = x; } await act(async () => { await new Promise((r) => setTimeout(r, 20)); }); } throw e; }
const ACCES = 'A'.repeat(43);
const INV = 'JetonBassi1234567890';

describe('V610p — arrivée par le lien de l’e-mail d’accès', () => {
  test('B/C/D — le lien ouvre l’ESPACE (session B3-S1), retient l’événement, nettoie l’adresse', async () => {
    window.history.replaceState({}, '', `/espace/AFR-TEST01?acces=${ACCES}&evt=OFF-1&inv=${INV}`);
    axios.post.mockImplementation((url) => (String(url).endsWith('/subscriber/acces/lien')
      ? Promise.resolve({ data: { success: true, token: 'jeton.espace.signe', expires_at: '2999-01-01T00:00:00+00:00', member_slug: null } })
      : Promise.resolve({ data: {} })));
    axios.get.mockResolvedValue({ data: { code: 'AFR-TEST01', name: 'Bassi', evenements_offerts: [] } });
    global.fetch = jest.fn(() => Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) }));
    await act(async () => { rendre(<SubscriberSpace />); });
    await attendre(() => expect(axios.post.mock.calls.some((c) => String(c[0]).endsWith('/subscriber/acces/lien'))).toBe(true));
    const appel = axios.post.mock.calls.find((c) => String(c[0]).endsWith('/subscriber/acces/lien'));
    expect(appel[1]).toEqual({ code: 'AFR-TEST01', acces: ACCES });
    expect(lireIntentionMembre()).toEqual({ offre: 'OFF-1', jeton: INV });                 // événement retenu
    expect(window.location.search).not.toMatch(/acces=|evt=|inv=/);                       // adresse nettoyée
    await attendre(() => expect(String(window.localStorage.getItem('afroboost_espace_token') || '')).toContain('jeton.espace.signe'));
    await attendre(() => expect(axios.get.mock.calls.some((c) => /\/subscriber\/space\/AFR-TEST01/.test(String(c[0])))).toBe(true));
    expect(document.body.innerHTML).not.toMatch(/chat-widget|ChatWidget/);
  });
  test('lien expiré / déjà utilisé : message clair, l’écran du code e-mail prend le relais', async () => {
    window.history.replaceState({}, '', `/espace/AFR-TEST01?acces=${ACCES}`);
    axios.post.mockRejectedValue({ response: { status: 400, data: { detail: 'Lien invalide ou expiré.' } } });
    await act(async () => { rendre(<SubscriberSpace />); });
    await attendre(() => expect(q('espace-lien-expire')).toBeTruthy());
    expect(q('espace-email')).toBeTruthy();
    expect(axios.get).not.toHaveBeenCalled();                                               // aucune donnée sans session
  });
});

describe('V610p — « Je suis membre » : l’événement voyage jusqu’à l’e-mail', () => {
  test('A — la demande d’accès porte l’offre et le jeton de l’invitation', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }));
    const avant = jest.fn();
    await act(async () => { rendre(<AccesMembreEvenement offreVisee="OFF-1" jetonInvitation={INV} avantOuverture={avant} />); });
    await act(async () => { q('acces-membre-bouton').click(); });
    const champ = q('acces-membre-email');
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(champ, 'bassi@test.example');
      champ.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => { champ.form.requestSubmit ? champ.form.requestSubmit() : champ.form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });
    await attendre(() => expect(global.fetch).toHaveBeenCalled());
    expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toEqual({ email: 'bassi@test.example', offre: 'OFF-1', jeton: INV });
    expect(avant).toHaveBeenCalled();
  });
});

describe('V610p — partage CONTEXTUEL de l’événement', () => {
  test('G/H — « Invite un ami à Afroboost Silent », date, lieu, tarif serveur, 50 PLACES ; aucune séance, aucun essai', async () => {
    await act(async () => { rendre(<PartagerInviter jeton={INV} lien="https://afroboost.com/i/x" texte="T" contexte={{
      titre: 'Afroboost Silent', quand: 'Mercredi 28 octobre · 18h45', ville: 'Neuchâtel', prix: '25 CHF', places: '50 PLACES', plusTot: true }} />); });
    await act(async () => { q('inviter-partager').click(); });
    const c = q('partager-contexte').textContent;
    expect(c).toContain('Invite un ami à Afroboost Silent');
    expect(c).toContain('Mercredi 28 octobre · 18h45 · Neuchâtel');
    expect(c).toContain('Tarif actuel de l’événement : 25 CHF');
    expect(c).toContain('50 PLACES');
    expect(c).toContain('Plus tu réserves tôt, moins c’est cher.');
    expect(document.body.textContent).not.toMatch(/essai|séance de ton ami|gratuit/i);
    expect(q('inviter-whatsapp')).toBeTruthy();
  });
});

describe('V610p — page de l’ami', () => {
  test('I/J — « Bassi t’invite à Afroboost Silent », prix public, « 50 PLACES » (message), jamais « essai »', async () => {
    global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({
      type: 'event_paid', title: 'AFROBOOST SILENT — ÉDITION SPÉCIALE', inviter_display: { prenom: 'Bassi' }, message_places: '50 PLACES',
      date_label: 'mercredi 28 octobre', time_label: '18:45', lieu: 'Chemin des Valangines 97, 2000 Neuchâtel',
      prix_actif: { prix: 25, palier: 'early_bird', libelle: 'Prévente' }, reservation_directe: { offer_id: 'OFF-1' } }) }));
    await act(async () => { rendre(<InvitationPublique token={INV} />); });
    await attendre(() => expect(q('inv-pub-inviteur')).toBeTruthy());
    expect(q('inv-pub-inviteur').textContent).toBe('Bassi t\'invite à Afroboost Silent');
    expect(q('inv-pub-prix-actif').textContent).toBe('25 CHF');
    expect(q('inv-pub-places').textContent).toContain('50 PLACES');
    expect(document.body.textContent).not.toMatch(/essai|premier cours/i);
    expect(document.body.textContent).not.toMatch(/places restantes|plus que \d+/i);
  });
});

describe('V610p — ancien lien /?qr= -> espace (jamais le ChatWidget)', () => {
  test('code AFR valide -> /espace/<CODE> ; sinon rien', () => {
    // eslint-disable-next-line global-require
    const { urlEspaceDuLienQr } = require('../../utils/espaceSession');
    expect(urlEspaceDuLienQr('afr-2287ca')).toBe('/espace/AFR-2287CA');
    expect(urlEspaceDuLienQr('AFR-<x>')).toBe('');
    expect(urlEspaceDuLienQr('https://evil.example')).toBe('');
  });
});

/**
 * F3 SUITE — LA CARTE COMPACTE VERS LE VRAI PROFIL SPORDATEUR.
 *
 * CE QU'ELLE PROUVE
 *   - lié          -> avatar + nom + « Gérer mon profil », le clic NAVIGUE
 *                     vers le pont avec next=/profile (auto-login préchargé) ;
 *   - le survol PRÉCHARGE le pont (entrée instantanée au clic) ;
 *   - non lié      -> « Profil social non encore activé », jamais un faux profil ;
 *   - indisponible -> la carte disparaît, l'espace reste utilisable ;
 *   - une simple lecture n'écrit RIEN (aucun POST/PUT/PATCH/DELETE de la carte).
 *
 * axios et le module de handoff sont mockés : aucun réseau, aucune navigation réelle.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import axios from 'axios';
import CarteProfilSpordateur from '../CarteProfilSpordateur';
import { prechargerSpordate, entrerDansSpordate } from '../../utils/spordateHandoff';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), patch: jest.fn(), delete: jest.fn() },
}));
jest.mock('../../utils/spordateHandoff', () => ({
  __esModule: true,
  prechargerSpordate: jest.fn(),
  entrerDansSpordate: jest.fn(),
}));

let conteneur, racine;
beforeEach(() => {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  jest.clearAllMocks();
});
afterEach(() => {
  if (racine) act(() => racine.unmount());
  conteneur.remove();
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);

async function monter(reponse) {
  axios.get.mockReturnValue(reponse);
  await act(async () => {
    racine = createRoot(conteneur);
    racine.render(React.createElement(CarteProfilSpordateur));
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
}

const PROFIL = {
  displayName: 'BASSI BASSI',
  photoURL: 'https://firebasestorage.googleapis.com/p0.jpg',
  photos: ['https://firebasestorage.googleapis.com/p0.jpg'],
  bio: 'Coach afrobeat.', city: 'Neuchâtel', canton: 'NE',
  sports: [{ name: 'Afroboost', level: 'advanced' }],
};

test('A. lié → avatar + nom + « Gérer mon profil »', async () => {
  await monter(Promise.resolve({ data: { lie: true, profil: PROFIL } }));
  expect(par('carte-nom').textContent).toBe('BASSI BASSI');
  expect(par('carte-avatar')).not.toBeNull();
  expect(par('carte-profil').textContent).toContain('Gérer mon profil');
});

test('B. le clic navigue vers le pont avec next=/profile', async () => {
  await monter(Promise.resolve({ data: { lie: true, profil: PROFIL } }));
  await act(async () => { par('carte-profil').click(); });
  expect(entrerDansSpordate).toHaveBeenCalledWith('/profile');
});

test('C. le survol précharge le pont', async () => {
  await monter(Promise.resolve({ data: { lie: true, profil: PROFIL } }));
  await act(async () => {
    par('carte-profil').dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
  });
  expect(prechargerSpordate).toHaveBeenCalled();
});

test('D. non lié → « Profil social non encore activé », jamais un faux profil', async () => {
  await monter(Promise.resolve({ data: { lie: false, motif: 'non_lie' } }));
  expect(par('carte-non-lie')).not.toBeNull();
  expect(par('carte-non-lie').textContent).toContain('non encore activé');
  expect(par('carte-nom')).toBeNull();
});

test('E. pont indisponible → la carte disparaît (rien à casser)', async () => {
  await monter(Promise.reject(new Error('boom')));
  expect(conteneur.querySelector('[data-testid="carte-profil"]')).toBeNull();
});

test('F. sans avatar (lié mais photos vides) → initiale, pas de plantage', async () => {
  await monter(Promise.resolve({ data: { lie: true, profil: { displayName: 'Solo', photos: [] } } }));
  expect(par('carte-avatar-vide').textContent).toBe('S');
  expect(par('carte-nom').textContent).toBe('Solo');
});

test('G. lecture pure → aucune écriture (post/put/patch/delete)', async () => {
  await monter(Promise.resolve({ data: { lie: true, profil: PROFIL } }));
  expect(axios.post).not.toHaveBeenCalled();
  expect(axios.put).not.toHaveBeenCalled();
  expect(axios.patch).not.toHaveBeenCalled();
  expect(axios.delete).not.toHaveBeenCalled();
});

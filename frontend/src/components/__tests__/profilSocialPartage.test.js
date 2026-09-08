/**
 * F2 — LE PANNEAU DE PROFIL SOCIAL, VU DU NAVIGATEUR.
 *
 * CE QU'IL PROUVE (K, L, N du GO)
 *   - lié          -> photo, nom, bio, lieu, sports affichés ;
 *   - non lié      -> invitation à relier, jamais une erreur ;
 *   - indisponible -> rien d'alarmant, l'espace reste utilisable ;
 *   - profil partiel / photos absentes -> UI saine, aucun plantage ;
 *   - une simple lecture n'écrit RIEN (aucun POST/PUT/PATCH/DELETE).
 *
 * axios est mocké : aucun appel réseau ne part.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import axios from 'axios';
import ProfilSocialPartage from '../ProfilSocialPartage';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), patch: jest.fn(), delete: jest.fn() },
}));

let conteneur;
let racine;
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
    racine.render(React.createElement(ProfilSocialPartage));
  });
  // laisser la promesse se résoudre
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
}

const PROFIL = {
  displayName: 'BASSI BASSI',
  photoURL: 'https://firebasestorage.googleapis.com/p0.jpg',
  photos: ['https://firebasestorage.googleapis.com/p0.jpg', 'https://firebasestorage.googleapis.com/p1.jpg'],
  bio: 'Coach afrobeat.', city: 'Neuchâtel', canton: 'NE',
  sports: [{ name: 'Afroboost', level: 'advanced' }],
};

test('A. lié → photo, nom, bio, lieu, sports affichés', async () => {
  await monter(Promise.resolve({ data: { lie: true, profil: PROFIL } }));
  expect(par('profil-nom').textContent).toBe('BASSI BASSI');
  expect(par('profil-bio').textContent).toContain('Coach afrobeat');
  expect(par('profil-lieu').textContent).toBe('Neuchâtel, NE');
  expect(par('profil-photo')).toBeTruthy();
  expect(par('profil-photo').getAttribute('src')).toBe(PROFIL.photoURL);
  expect(par('profil-sports').textContent).toContain('Afroboost');
});

test("B. une lecture n'écrit RIEN", async () => {
  await monter(Promise.resolve({ data: { lie: true, profil: PROFIL } }));
  expect(axios.get).toHaveBeenCalledTimes(1);
  expect(axios.get.mock.calls[0][0]).toContain('/spordate/unified-profile/me');
  expect(axios.post).not.toHaveBeenCalled();
  expect(axios.put).not.toHaveBeenCalled();
  expect(axios.patch).not.toHaveBeenCalled();
  expect(axios.delete).not.toHaveBeenCalled();
});

test('C. non lié → invitation à relier, pas d’erreur', async () => {
  await monter(Promise.resolve({ data: { lie: false, motif: 'non_lie' } }));
  expect(par('profil-non-lie')).toBeTruthy();
  expect(par('profil-non-lie').textContent).toContain('pas encore relié');
  expect(par('profil-nom')).toBeNull();
});

test('D. pont indisponible → composant discret (rien), espace intact', async () => {
  await monter(Promise.reject(new Error('réseau')));
  // dégradation douce : le composant ne rend rien plutôt qu'une erreur.
  expect(par('profil-social')).toBeNull();
});

test('E. profil partiel (ni photo ni bio ni sports) → UI saine', async () => {
  await monter(Promise.resolve({ data: { lie: true, profil: {
    displayName: 'Solo', photoURL: null, photos: [], bio: '', city: '', canton: '', sports: [],
  } } }));
  expect(par('profil-nom').textContent).toBe('Solo');
  // pas de photo → avatar initiale, jamais une image cassée
  expect(par('profil-photo')).toBeNull();
  expect(par('profil-photo-vide').textContent).toBe('S');
  expect(par('profil-bio')).toBeNull();
  expect(par('profil-sports')).toBeNull();
  expect(par('profil-galerie')).toBeNull();
});

test('F. photos absentes mais photoURL présent → une seule photo, pas de galerie', async () => {
  await monter(Promise.resolve({ data: { lie: true, profil: {
    displayName: 'X', photoURL: 'https://s/only.jpg', photos: ['https://s/only.jpg'],
    bio: '', city: 'Lausanne', canton: '', sports: [],
  } } }));
  expect(par('profil-photo').getAttribute('src')).toBe('https://s/only.jpg');
  expect(par('profil-galerie')).toBeNull(); // une seule photo → pas de galerie
  expect(par('profil-lieu').textContent).toBe('Lausanne');
});

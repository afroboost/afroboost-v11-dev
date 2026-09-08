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

async function monter(reponse, activationOn = true) {
  // Deux GET distincts : le profil unifié, et le drapeau F4 (feature-flags).
  axios.get.mockImplementation((url) => {
    if (String(url).includes('feature-flags')) {
      return Promise.resolve({ data: { SOCIAL_ACTIVATION_ENABLED: activationOn } });
    }
    return reponse;
  });
  await act(async () => {
    racine = createRoot(conteneur);
    racine.render(React.createElement(CarteProfilSpordateur));
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
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

test('D0. F4 DORMANT (flag OFF) → carte passive « non encore activé », pas d’activation', async () => {
  await monter(Promise.resolve({ data: { lie: false, motif: 'non_lie' } }), false);
  expect(par('carte-non-lie')).not.toBeNull();
  expect(par('carte-non-lie').textContent).toContain('non encore activé');
  expect(par('carte-activer')).toBeNull();
});

test('D. non lié → carte d’ACTIVATION (F4), jamais un faux profil', async () => {
  await monter(Promise.resolve({ data: { lie: false, motif: 'non_lie' } }));
  expect(par('carte-activer')).not.toBeNull();
  expect(par('carte-activer-titre').textContent).toContain('Profil social');
  expect(par('carte-nom')).toBeNull();       // aucun profil d'autrui inventé
});

test('D2. F4 — consentement NON pré-coché ; « Activer » désactivé tant que non coché', async () => {
  await monter(Promise.resolve({ data: { lie: false, motif: 'non_lie' } }));
  await act(async () => { par('carte-activer').click(); });      // ouvre le consentement
  const caseConsent = par('carte-consent-case');
  expect(caseConsent).not.toBeNull();
  expect(caseConsent.checked).toBe(false);                       // JAMAIS pré-coché
  expect(par('carte-activer-confirmer').disabled).toBe(true);    // bloqué sans consentement
  expect(axios.post).not.toHaveBeenCalled();                     // rien envoyé
});

test('D3. F4 — consentement coché + Activer → POST /spordate/activate {consent:true}', async () => {
  axios.post.mockResolvedValue({ data: { url: '/rencontre/activer?t=JETON' } });
  await monter(Promise.resolve({ data: { lie: false, motif: 'non_lie' } }));
  await act(async () => { par('carte-activer').click(); });
  await act(async () => { par('carte-consent-case').click(); });   // bascule native + onChange
  await act(async () => { par('carte-activer-confirmer').click(); });
  expect(axios.post).toHaveBeenCalledWith(
    expect.stringContaining('/spordate/activate'),
    { consent: true },
  );
});

test('D4. F4 — « Plus tard » masque la carte, l’espace reste utilisable (État C)', async () => {
  await monter(Promise.resolve({ data: { lie: false, motif: 'non_lie' } }));
  await act(async () => { par('carte-plus-tard').click(); });
  expect(par('carte-profil')).toBeNull();
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

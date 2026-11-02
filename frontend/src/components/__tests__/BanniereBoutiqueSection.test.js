/**
 * V645.3 — « Bannière Boutique — Accueil ».
 * Vérifie la PROPRIÉTÉ CLÉ exigée par Bassi : la bannière est INDÉPENDANTE du
 * T-shirt. L'enregistrement ne touche QUE concept.home_shop_banner_url/_type
 * (PUT /concept), jamais l'offre ; retirer la bannière vide bien les deux champs.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';

jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn(), put: jest.fn() } }));
// L'éditeur vidéo et le bouton d'upload sont remplacés par des stubs légers :
// on ne teste pas leur rendu ici (déjà couvert), mais le câblage d'enregistrement.
jest.mock('../VideoTrimEditor', () => ({ __esModule: true, default: () => null }));
jest.mock('../CloudinaryUploadButton', () => {
  const R = require('react');
  const Btn = (props) => R.createElement('button', {
    'data-testid': props['data-testid'],
    onClick: () => props.onUpload('/api/files/banniere/image_x.jpg'),
  }, 'upload');
  return { __esModule: true, default: Btn, uploadToCloudinary: jest.fn(async () => ({ url: '/api/files/thumb.jpg' })) };
});

import axios from 'axios';
import BanniereBoutiqueSection from '../dashboard/BanniereBoutiqueSection';

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

let conteneur, racine;
async function monter() {
  axios.get.mockResolvedValue({ data: { home_shop_banner_url: '', home_shop_banner_type: '' } });
  axios.put.mockResolvedValue({ data: {} });
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(<BanniereBoutiqueSection API="/api" />); });
  // laisser la lecture GET /concept se résoudre
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
}
function clic(testid) {
  const el = conteneur.querySelector(`[data-testid="${testid}"]`);
  if (!el) throw new Error('introuvable: ' + testid);
  return act(async () => { el.dispatchEvent(new MouseEvent('click', { bubbles: true })); await Promise.resolve(); });
}
afterEach(() => { if (racine) act(() => racine.unmount()); if (conteneur) conteneur.remove(); jest.clearAllMocks(); });

test('la section lit la bannière via GET /concept', async () => {
  await monter();
  expect(axios.get).toHaveBeenCalledWith('/api/concept');
  expect(conteneur.querySelector('[data-testid="banniere-boutique-section"]')).toBeTruthy();
});

test('enregistrer une image → PUT /concept avec home_shop_banner_* UNIQUEMENT (indépendant du T-shirt)', async () => {
  await monter();
  await clic('banniere-boutique-upload');   // import d'une image
  await clic('banniere-boutique-enregistrer');
  await act(async () => { await Promise.resolve(); });
  expect(axios.put).toHaveBeenCalledTimes(1);
  const [url, payload] = axios.put.mock.calls[0];
  expect(url).toBe('/api/concept');
  expect(payload).toEqual({
    home_shop_banner_url: '/api/files/banniere/image_x.jpg',
    home_shop_banner_type: 'image',
  });
  // INDÉPENDANCE : aucun champ d'offre ne part dans la requête bannière.
  const interdits = ['videoUrl', 'images', 'thumbnail', 'price', 'name', 'variants', 'isProduct'];
  interdits.forEach(k => expect(payload).not.toHaveProperty(k));
});

test('retirer la bannière → PUT /concept avec les deux champs vidés', async () => {
  axios.get.mockResolvedValue({ data: { home_shop_banner_url: '/api/files/old.jpg', home_shop_banner_type: 'image' } });
  conteneur = document.createElement('div'); document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  axios.put.mockResolvedValue({ data: {} });
  await act(async () => { racine.render(<BanniereBoutiqueSection API="/api" />); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  await clic('banniere-boutique-retirer');
  await act(async () => { await Promise.resolve(); });
  const [url, payload] = axios.put.mock.calls[0];
  expect(url).toBe('/api/concept');
  expect(payload).toEqual({ home_shop_banner_url: '', home_shop_banner_type: '' });
});

/**
 * V645.3 — « Bannière Boutique — Accueil ».
 * Vérifie la PROPRIÉTÉ CLÉ exigée par Bassi : la bannière est INDÉPENDANTE du
 * T-shirt. L'enregistrement ne touche QUE concept.home_shop_banner_url/_type
 * (PUT /concept), jamais l'offre ; retirer la bannière vide bien les deux champs.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';

jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn(), put: jest.fn() } }));
// VideoTrimEditor — stub qui expose un bouton de capture pour les tests miniature.
jest.mock('../VideoTrimEditor', () => {
  const R = require('react');
  const VTE = (props) => R.createElement('div', { 'data-testid': 'vte-mock' },
    R.createElement('button', {
      'data-testid': 'vte-mock-capture',
      onClick: () => props.onThumbnailCapture && props.onThumbnailCapture(
        new Blob(['img'], { type: 'image/jpeg' }),
        'blob:test-preview'
      ),
    }, 'capturer'),
  );
  return { __esModule: true, default: VTE };
});
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
import { uploadToCloudinary } from '../CloudinaryUploadButton';

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
  // V645.3c — image : découpe neutralisée (0/0) + pas de poster.
  expect(payload).toEqual({
    home_shop_banner_url: '/api/files/banniere/image_x.jpg',
    home_shop_banner_type: 'image',
    home_shop_banner_trim_start: 0,
    home_shop_banner_trim_end: 0,
    home_shop_banner_thumbnail: '',
    // V645.4k — cadrage toujours envoyé ; neutre tant qu'on n'a pas recadré.
    home_shop_banner_crop: { x: 0.5, y: 0.5, zoom: 1 },
  });
  // INDÉPENDANCE : aucun champ d'offre ne part dans la requête bannière.
  const interdits = ['videoUrl', 'images', 'thumbnail', 'price', 'name', 'variants', 'isProduct'];
  interdits.forEach(k => expect(payload).not.toHaveProperty(k));
});

// Helper : monter avec une bannière vidéo existante (pour tester la miniature).
async function monterAvecVideo() {
  axios.get.mockResolvedValue({ data: {
    home_shop_banner_url: '/api/files/v/video.mp4',
    home_shop_banner_type: 'video',
    home_shop_banner_trim_start: 0, home_shop_banner_trim_end: 0,
    home_shop_banner_thumbnail: '/api/files/old-thumb.jpg',
  }});
  axios.put.mockResolvedValue({ data: {} });
  conteneur = document.createElement('div'); document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(<BanniereBoutiqueSection API="/api" />); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
}

// ── FIX 1 : capture miniature seule → formulaire modifié (bouton activé) ─────
test('capturer miniature sans changer la découpe → Enregistrer devient actif', async () => {
  await monterAvecVideo();
  const btnSave = conteneur.querySelector('[data-testid="banniere-boutique-enregistrer"]');
  // Initialement : bannière non modifiée → bouton désactivé.
  expect(btnSave.disabled).toBe(true);
  // Clic sur capture dans le VTE.
  await clic('vte-mock-capture');
  // Après capture : formulaire doit être marqué modifié.
  expect(btnSave.disabled).toBe(false);
});

// ── FIX 2a : Enregistrer bloqué pendant l'upload de la miniature ──────────────
test('Enregistrer bloqué tant que la miniature est en cours d\'upload', async () => {
  await monterAvecVideo();
  // Upload bloqué en attente.
  let resolveUpload;
  uploadToCloudinary.mockImplementationOnce(() => new Promise((res) => { resolveUpload = res; }));
  // Lancer la capture (déclenche l'upload).
  await clic('vte-mock-capture');
  const btnSave = conteneur.querySelector('[data-testid="banniere-boutique-enregistrer"]');
  // Pendant l'envoi : bouton doit être désactivé.
  expect(btnSave.disabled).toBe(true);
  // Indicateur visible.
  expect(conteneur.querySelector('[data-testid="banniere-boutique-mini-envoi"]')).toBeTruthy();
  // Débloquer l'upload.
  await act(async () => { resolveUpload({ url: '/api/files/new-thumb.jpg' }); await Promise.resolve(); await Promise.resolve(); });
  // Après upload : bouton activé (formulaire modifié).
  expect(btnSave.disabled).toBe(false);
});

// ── FIX 2b : échec upload miniature → erreur + ancienne miniature préservée ───
test('échec upload miniature → erreur affichée, ancienne miniature préservée dans le payload', async () => {
  await monterAvecVideo();
  uploadToCloudinary.mockRejectedValueOnce(new Error('network'));
  await clic('vte-mock-capture');
  await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
  // Message d'erreur visible.
  expect(conteneur.querySelector('[data-testid="banniere-boutique-mini-erreur"]')).toBeTruthy();
  // Le formulaire reste modifié (capture = intention).
  const btnSave = conteneur.querySelector('[data-testid="banniere-boutique-enregistrer"]');
  expect(btnSave.disabled).toBe(false);
  // Enregistrer → le payload ne contient PAS une blob: URL.
  await clic('banniere-boutique-enregistrer');
  await act(async () => { await Promise.resolve(); });
  const payload = axios.put.mock.calls[0][1];
  expect(payload.home_shop_banner_thumbnail).not.toMatch(/^blob:/);
  // L'ancienne miniature est restaurée dans le payload.
  expect(payload.home_shop_banner_thumbnail).toBe('/api/files/old-thumb.jpg');
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
  // V645.3c — retirer vide aussi découpe + miniature.
  expect(payload).toEqual({
    home_shop_banner_url: '', home_shop_banner_type: '',
    home_shop_banner_trim_start: 0, home_shop_banner_trim_end: 0, home_shop_banner_thumbnail: '',
    home_shop_banner_crop: { x: 0.5, y: 0.5, zoom: 1 },
  });
});

/**
 * V533 — CampaignMediaUploader : progression réelle, états, annulation/retry,
 * aperçu vidéo, miniature (frame vidéo / import image / recadrage 9:16),
 * persistance via onChange. Aucun réseau : `uploadToCloudinary` est mocké et
 * rejoue une progression contrôlée ; la capture de frame est mockée.
 */
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';

const upload = { impl: null };
jest.mock('../../CloudinaryUploadButton', () => ({
  __esModule: true,
  default: () => null,
  uploadToCloudinary: (file, opts) => upload.impl(file, opts),
}));
const capture = { blob: null };
jest.mock('../../VideoTrimEditor', () => ({
  __esModule: true,
  default: () => null,
  attendreFrame: () => Promise.resolve(),
  capturerFrame: () => Promise.resolve(capture.blob),
}));
jest.mock('react-easy-crop', () => {
  const mockReact = require('react');
  return {
    __esModule: true,
    default: ({ onCropComplete }) => {
      // Simule un cadre 9:16 centré déjà calculé par la bibliothèque.
      // Une seule fois : la vraie bibliothèque n'appelle onCropComplete qu'à la fin d'un geste.
      mockReact.useEffect(() => { onCropComplete({}, { x: 480, y: 0, width: 607, height: 1080 }); }, []); // eslint-disable-line react-hooks/exhaustive-deps
      return mockReact.createElement('div', { 'data-testid': 'fake-cropper' });
    },
  };
});
jest.mock('../../../utils/miniatureReel', () => {
  const reel = jest.requireActual('../../../utils/miniatureReel');
  return { ...reel, recadrerImage: () => Promise.resolve(new Blob(['jpg'], { type: 'image/jpeg' })) };
});

const CampaignMediaUploader = require('../CampaignMediaUploader').default;

let racine; let conteneur; let dernier;
function Harnais({ initial }) {
  const [c, setC] = useState(initial || { mediaUrl: '', mediaFormat: '16:9', thumbnail_url: '', thumbnail_source: null, thumbnail_time: null });
  const [busy, setBusy] = useState(false);
  dernier = { c, busy };
  return (
    <div>
      <CampaignMediaUploader mediaUrl={c.mediaUrl} thumbnailUrl={c.thumbnail_url} thumbnailSource={c.thumbnail_source} thumbnailTime={c.thumbnail_time}
        onChange={(patch) => setC((prev) => ({ ...prev, ...patch }))} onBusyChange={setBusy}
        onFormatDetected={(fmt) => setC((prev) => ({ ...prev, mediaFormat: fmt }))} />
      <button type="button" data-testid="suivant" disabled={busy}>Suivant</button>
    </div>
  );
}
const q = (sel) => conteneur.querySelector(sel);
const texte = (sel) => (q(sel) ? q(sel).textContent : null);
async function monter(initial) { await act(async () => { racine.render(<Harnais initial={initial} />); }); }
async function choisirFichier(file) {
  const input = q('[data-testid="v533-input-video"]');
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  await act(async () => { input.dispatchEvent(new Event('change', { bubbles: true })); });
}
const defer = () => { let r, j; const p = new Promise((a, b) => { r = a; j = b; }); return { p, r, j }; };

beforeEach(() => {
  conteneur = document.createElement('div'); document.body.appendChild(conteneur); racine = createRoot(conteneur);
  global.URL.createObjectURL = jest.fn(() => 'blob:miniature');
  upload.impl = null; capture.blob = null;
});
afterEach(() => { act(() => racine.unmount()); conteneur.remove(); });

test('A. petite vidéo : nom/taille/type, progression 0→100 %, « Vidéo envoyée », aperçu, Suivant bloqué pendant l\'envoi', async () => {
  const d = defer();
  upload.impl = async (file, opts) => { opts.onProgress(12); opts.onProgress(37); await d.p; opts.onProgress(100); return { url: '/api/files/abc/clip.mp4', resourceType: 'video' }; };
  await monter();
  expect(texte('[data-testid="v533-etat"]')).toBe('Choisir une vidéo');
  await choisirFichier(new File([new Uint8Array(1024 * 1024)], 'petite.mp4', { type: 'video/mp4' }));
  expect(texte('[data-testid="v533-fichier"]')).toMatch(/petite\.mp4/);
  expect(texte('[data-testid="v533-fichier"]')).toMatch(/1,0 Mo/);
  expect(texte('[data-testid="v533-fichier"]')).toMatch(/video\/mp4/);
  expect(texte('[data-testid="v533-etat"]')).toBe('Envoi de la vidéo… 37 %');
  expect(q('[data-testid="v533-barre"]').getAttribute('aria-valuenow')).toBe('37');
  expect(q('[data-testid="suivant"]').disabled).toBe(true);
  await act(async () => { d.r(); });
  expect(texte('[data-testid="v533-etat"]')).toBe('Vidéo envoyée');
  expect(dernier.c.mediaUrl).toBe('/api/files/abc/clip.mp4');
  expect(q('[data-testid="v533-video"]')).not.toBeNull();
  expect(q('[data-testid="suivant"]').disabled).toBe(false);
});

test('B. grosse vidéo : la progression évolue réellement (valeurs distinctes, croissantes), jamais une animation fictive', async () => {
  const etapes = [3, 18, 44, 71, 96];
  const vus = [];
  upload.impl = async (file, opts) => {
    for (const p of etapes) { opts.onProgress(p); await new Promise((r) => setTimeout(r, 0)); vus.push(p); }
    return { url: '/api/files/x/grosse.mp4', resourceType: 'video' };
  };
  await monter();
  await choisirFichier(new File([new Uint8Array(10)], 'grosse.mp4', { type: 'video/mp4' }));
  expect(vus).toEqual(etapes);
  expect(texte('[data-testid="v533-etat"]')).toBe('Vidéo envoyée');
});

test('C. échec : message humain + Réessayer, puis succès au second essai', async () => {
  let n = 0;
  upload.impl = async () => { n += 1; if (n === 1) throw new Error("Connexion interrompue pendant l'envoi."); return { url: '/api/files/y/ok.mp4', resourceType: 'video' }; };
  await monter();
  await choisirFichier(new File([new Uint8Array(10)], 'ko.mp4', { type: 'video/mp4' }));
  expect(texte('[data-testid="v533-etat"]')).toMatch(/L'envoi a échoué — Connexion interrompue/);
  expect(q('[data-testid="v533-reessayer"]')).not.toBeNull();
  expect(dernier.c.mediaUrl).toBe('');
  await act(async () => { q('[data-testid="v533-reessayer"]').click(); });
  expect(n).toBe(2);
  expect(dernier.c.mediaUrl).toBe('/api/files/y/ok.mp4');
});

test('C bis. Annuler pendant l\'envoi : état « Envoi annulé », rien n\'est enregistré', async () => {
  upload.impl = (file, opts) => new Promise((_, rej) => { opts.onProgress(20); opts.signal.addEventListener('abort', () => rej(new Error('Envoi annulé.'))); });
  await monter();
  await choisirFichier(new File([new Uint8Array(10)], 'a.mp4', { type: 'video/mp4' }));
  expect(q('[data-testid="v533-annuler"]')).not.toBeNull();
  await act(async () => { q('[data-testid="v533-annuler"]').click(); });
  expect(texte('[data-testid="v533-etat"]')).toBe('Envoi annulé');
  expect(dernier.c.mediaUrl).toBe('');
  expect(q('[data-testid="suivant"]').disabled).toBe(false);
});

async function preparerVideo(w, h, duree) {
  upload.impl = async (file) => (file.name === 'miniature-reel.jpg'
    ? { url: '/api/files/t/miniature-reel.jpg', resourceType: 'image' }
    : { url: '/api/files/v/reel.mp4', resourceType: 'video' });
  await monter();
  await choisirFichier(new File([new Uint8Array(10)], 'reel.mp4', { type: 'video/mp4' }));
  const v = q('[data-testid="v533-video"]');
  Object.defineProperty(v, 'videoWidth', { value: w, configurable: true });
  Object.defineProperty(v, 'videoHeight', { value: h, configurable: true });
  Object.defineProperty(v, 'duration', { value: duree, configurable: true });
  await act(async () => { v.dispatchEvent(new Event('loadedmetadata')); });
  return v;
}

test('D. frame à 5 s d\'une vidéo 9:16 → miniature capturée, persistée avec source video_frame et temps 5', async () => {
  capture.blob = new Blob(['frame'], { type: 'image/jpeg' });
  const v = await preparerVideo(1080, 1920, 32.2);
  expect(texte('[data-testid="v533-infos"]')).toMatch(/0:32/);
  expect(q('[data-testid="v533-format-reel"]')).not.toBeNull();
  expect(dernier.c.mediaFormat).toBe('9:16');
  const curseur = q('[data-testid="v533-curseur"]');
  await act(async () => { curseur.value = '5'; curseur.dispatchEvent(new Event('input', { bubbles: true })); curseur.dispatchEvent(new Event('change', { bubbles: true })); });
  Object.defineProperty(v, 'currentTime', { value: 5, configurable: true, writable: true });
  await act(async () => { q('[data-testid="v533-capturer"]').click(); });
  expect(dernier.c.thumbnail_url).toBe('/api/files/t/miniature-reel.jpg');
  expect(dernier.c.thumbnail_source).toBe('video_frame');
  expect(dernier.c.thumbnail_time).toBe(5);
  expect(q('[data-testid="v533-miniature"]')).not.toBeNull();
  expect(q('[data-testid="v533-apercu-reel"]')).not.toBeNull();
  expect(q('[data-testid="v533-apercu-grille"]')).not.toBeNull();
  // Zones sûres : overlay affichable
  await act(async () => { q('[data-testid="v533-zones-sures"]').click(); });
  expect(q('[data-testid="v533-overlay-zones"]')).not.toBeNull();
});

test('E. importer un JPG paysage → recadrage 9:16 → miniature enregistrée (source upload)', async () => {
  await preparerVideo(1080, 1920, 10);
  const input = q('[data-testid="v533-input-image"]');
  Object.defineProperty(input, 'files', { value: [new File([new Uint8Array(10)], 'photo.jpg', { type: 'image/jpeg' })], configurable: true });
  await act(async () => { input.dispatchEvent(new Event('change', { bubbles: true })); });
  expect(q('[data-testid="v533-cropper"]')).not.toBeNull();          // F : le cadre 9:16 est proposé
  await act(async () => { q('[data-testid="v533-crop-valider"]').click(); });
  expect(q('[data-testid="v533-cropper"]')).toBeNull();
  expect(dernier.c.thumbnail_url).toBe('/api/files/t/miniature-reel.jpg');
  expect(dernier.c.thumbnail_source).toBe('upload');
  expect(dernier.c.thumbnail_time).toBeNull();
});

test('E bis. un fichier non image (gif/svg) est refusé avec un message, sans recadrage', async () => {
  await preparerVideo(1080, 1920, 10);
  const input = q('[data-testid="v533-input-image"]');
  Object.defineProperty(input, 'files', { value: [new File([new Uint8Array(10)], 'anim.gif', { type: 'image/gif' })], configurable: true });
  await act(async () => { input.dispatchEvent(new Event('change', { bubbles: true })); });
  expect(q('[data-testid="v533-cropper"]')).toBeNull();
  expect(conteneur.textContent).toMatch(/JPG, JPEG, PNG, WEBP/);
});

test('F. frame d\'une vidéo PAYSAGE → le recadrage 9:16 s\'ouvre avant d\'enregistrer', async () => {
  capture.blob = new Blob(['frame'], { type: 'image/jpeg' });
  await preparerVideo(1920, 1080, 10);
  expect(q('[data-testid="v533-format-reel"]')).toBeNull();
  await act(async () => { q('[data-testid="v533-capturer"]').click(); });
  expect(q('[data-testid="v533-cropper"]')).not.toBeNull();
  await act(async () => { q('[data-testid="v533-crop-valider"]').click(); });
  expect(dernier.c.thumbnail_source).toBe('video_frame');
});

test('G. rouvrir une campagne : vidéo + miniature conservées, « Remplacer la vidéo » proposé, aucun envoi déclenché', async () => {
  upload.impl = jest.fn();
  await monter({ mediaUrl: '/api/files/v/reel.mp4', mediaFormat: '9:16', thumbnail_url: '/api/files/t/min.jpg', thumbnail_source: 'video_frame', thumbnail_time: 7.3 });
  expect(texte('[data-testid="v533-etat"]')).toBe('Vidéo prête');
  expect(q('[data-testid="v533-video"]').getAttribute('src')).toBe('/api/files/v/reel.mp4');
  expect(q('[data-testid="v533-miniature"]').getAttribute('data-temps')).toBe('7.3');
  expect(q('[data-testid="v533-remplacer"]')).not.toBeNull();
  expect(upload.impl).not.toHaveBeenCalled();
});

test('H. nouvelle vidéo → l\'ancienne miniature est effacée (elle ne correspond plus)', async () => {
  upload.impl = async () => ({ url: '/api/files/v2/autre.mp4', resourceType: 'video' });
  await monter({ mediaUrl: '/api/files/v/reel.mp4', mediaFormat: '9:16', thumbnail_url: '/api/files/t/min.jpg', thumbnail_source: 'upload', thumbnail_time: null });
  await choisirFichier(new File([new Uint8Array(10)], 'autre.mp4', { type: 'video/mp4' }));
  expect(dernier.c.mediaUrl).toBe('/api/files/v2/autre.mp4');
  expect(dernier.c.thumbnail_url).toBe('');
  expect(dernier.c.thumbnail_source).toBeNull();
});

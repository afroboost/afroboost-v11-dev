/**
 * Nouvelle publication (ChatWidget) — le MÊME éditeur vidéo que « Modifier
 * l'offre » : découpe, aperçu de l'extrait, capture de miniature, et les
 * bornes envoyées avec la publication. Le mur joue l'extrait, jamais 00:00.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import { PublishModal, PublicationsCarousel } from '../Publications';

jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), put: jest.fn() } }));
jest.mock('react-easy-crop', () => () => null);

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

let conteneur, racine;
beforeEach(() => {
  HTMLCanvasElement.prototype.getContext = () => ({ drawImage: () => {} });
  HTMLCanvasElement.prototype.toBlob = function (cb) { cb(new Blob(['jpg'], { type: 'image/jpeg' })); };
  window.URL.createObjectURL = jest.fn(() => 'blob:local');
  window.URL.revokeObjectURL = jest.fn();
  if (typeof URL !== 'undefined') { URL.createObjectURL = window.URL.createObjectURL; URL.revokeObjectURL = window.URL.revokeObjectURL; }
  window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  // Les envois de fichiers : XHR simulé (media puis miniature).
  global.XMLHttpRequest = function () {
    const xhr = { upload: {}, responseText: '', status: 200 };
    xhr.open = () => {}; xhr.setRequestHeader = () => {};
    xhr.send = () => { setTimeout(() => { xhr.responseText = JSON.stringify({ url: '/api/files/pub/video_pub.mp4' }); if (xhr.onload) xhr.onload(); }, 5); };
    return xhr;
  };
  global.fetch = jest.fn(async () => ({ ok: true, status: 200, json: async () => ({ url: '/api/files/pub/video_pub.mp4' }), text: async () => JSON.stringify({ url: '/api/files/pub/video_pub.mp4' }) }));
});
async function monter(el) {
  conteneur = document.createElement('div'); document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(el); });
}
afterEach(async () => { if (racine) await act(async () => { racine.unmount(); }); if (conteneur) conteneur.remove(); });
const par = (id) => document.querySelector(`[data-testid="${id}"]`);
async function glisser(id, valeur) {
  const el = par(id);
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  await act(async () => { setter.call(el, String(valeur)); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); });
}

test('vidéo choisie → l’éditeur partagé (découpe + aperçu + capture) ; publier envoie trim_start / trim_end', async () => {
  axios.post.mockResolvedValue({ data: { id: 'pub-1' } });
  axios.get.mockResolvedValue({ data: [] });
  localStorage.setItem('afroboost_coach_user', JSON.stringify({ email: 'coach@example.com' }));   // l'envoi exige une session
  await monter(<PublishModal subscriberCode="AFR-TEST" onClose={() => {}} onPublished={() => {}} />);
  // Choix d'un fichier vidéo : la sonde de durée est un <video> hors DOM ; on
  // déclenche son onloadedmetadata via le prototype (durée 21 s).
  const original = document.createElement;
  const sondes = [];
  document.createElement = function (tag, ...r) { const el = original.call(document, tag, ...r); if (tag === 'video') sondes.push(el); return el; };
  const input = document.querySelector('input[type=file]');
  const fichier = new File(['x'], 'clip.mp4', { type: 'video/mp4' });
  Object.defineProperty(input, 'files', { configurable: true, get: () => [fichier] });
  await act(async () => { input.dispatchEvent(new Event('change', { bubbles: true })); });
  document.createElement = original;
  const sonde = sondes[0];
  Object.defineProperty(sonde, 'duration', { configurable: true, get: () => 21 });
  await act(async () => { sonde.onloadedmetadata(); });
  expect(par('publish-video-editor')).not.toBeNull();
  expect(par('video-trim-editor')).not.toBeNull();
  expect(document.body.textContent).toMatch(/Capturer cette image comme miniature/);
  // Métadonnées de l'aperçu, découpe 3 → 18.
  const v = par('vte-apercu').querySelector('video');
  Object.defineProperty(v, 'duration', { configurable: true, get: () => 21 });
  Object.defineProperty(v, 'videoWidth', { configurable: true, get: () => 1080 });
  Object.defineProperty(v, 'videoHeight', { configurable: true, get: () => 1920 });
  Object.defineProperty(v, 'readyState', { configurable: true, get: () => 2 });
  v.play = () => Promise.resolve(); v.pause = () => {};
  await act(async () => { v.dispatchEvent(new Event('loadedmetadata')); v.dispatchEvent(new Event('seeked')); await new Promise((r) => setTimeout(r, 30)); });
  await glisser('vte-start', 3);
  await glisser('vte-end', 18);
  expect(par('vte-extrait').textContent).toBe('00:15');
  // Miniature par défaut capturée automatiquement (pas d'image noire à 0 s).
  expect(par('vte-miniature-apercu')).not.toBeNull();
  // Publier.
  const publier = [...document.querySelectorAll('button')].find((b) => /^Publier/.test((b.textContent || '').trim()));
  expect(publier).toBeTruthy();
  // À l'envoi, une sonde <video> mesure la durée du fichier (jamais d'événement
  // en jsdom) : on la fait aboutir à la main.
  const sondesEnvoi = [];
  document.createElement = function (tag, ...r) { const el = original.call(document, tag, ...r); if (tag === 'video') sondesEnvoi.push(el); return el; };
  await act(async () => { publier.click(); await new Promise((r) => setTimeout(r, 20)); });
  document.createElement = original;
  await act(async () => {
    sondesEnvoi.forEach((el) => { Object.defineProperty(el, 'duration', { configurable: true, get: () => 21 }); if (el.onloadedmetadata) el.onloadedmetadata(); });
    await new Promise((r) => setTimeout(r, 60));
    sondesEnvoi.forEach((el) => { if (el.onloadedmetadata) el.onloadedmetadata(); });
    await new Promise((r) => setTimeout(r, 60));
  });
  expect(axios.post).toHaveBeenCalled();
  const payload = axios.post.mock.calls[0][1];
  expect(payload.media_type).toBe('video');
  expect(payload.trim_start).toBe(3);
  expect(payload.trim_end).toBe(18);
  expect(payload.thumbnail_url).toBe('/api/files/pub/video_pub.mp4');   // miniature envoyée (URL simulée)
});

test('le mur : une publication découpée 3 → 18 se joue depuis 3 s et reboucle à 18 s, jamais 00:00', async () => {
  const pub = { id: 'p1', media_type: 'video', media_url: '/api/files/pub/video_pub.mp4', thumbnail_url: '', trim_start: 3, trim_end: 18, display_name: 'Léa', created_at: new Date().toISOString(), expires_at: new Date(Date.now() + 3600e3).toISOString() };
  await monter(<PublicationsCarousel publications={[pub]} actions={{ likesCount: 0, liked: false, onLike: () => {}, commentsCount: 0, onComments: () => {}, comments: [], onReserve: () => {} }} />);
  const v = conteneur.querySelector('video');
  expect(v).not.toBeNull();
  v.play = () => Promise.resolve();
  v.currentTime = 0; await act(async () => { v.dispatchEvent(new Event('loadedmetadata')); });
  expect(v.currentTime).toBe(3);
  v.currentTime = 18.2; await act(async () => { v.dispatchEvent(new Event('timeupdate')); });
  expect(v.currentTime).toBe(3);
});

test('✏️ modifier une publication vidéo existante : éditeur préchargé (trim 0 → 20, miniature), nouveau trim 4 → 16 enregistré par PUT sans réupload', async () => {
  const pub = { id: 'pub-9', media_type: 'video', media_url: '/api/files/pub/video_pub.mp4', thumbnail_url: '/api/files/pub/image_mini.jpg', trim_start: 0, trim_end: 20, caption: 'Ancienne légende', display_name: 'Coach', created_at: new Date().toISOString(), expires_at: new Date(Date.now() + 3600e3).toISOString(), remaining_hours: 40 };
  axios.get.mockResolvedValue({ data: [pub] });
  axios.put.mockResolvedValue({ data: { status: 'ok' } });
  await monter(<PublishModal subscriberCode="" onClose={() => {}} onPublished={() => {}} />);
  await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
  const crayon = document.querySelector('button[aria-label="Modifier"]');
  expect(crayon).not.toBeNull();
  await act(async () => { crayon.click(); });
  expect(par('publish-modal').getAttribute('data-mode')).toBe('edition');
  expect(par('video-trim-editor')).not.toBeNull();
  expect(par('vte-apercu').querySelector('video').getAttribute('src')).toBe('/api/files/pub/video_pub.mp4');
  expect(par('vte-miniature-apercu').getAttribute('src')).toBe('/api/files/pub/image_mini.jpg');
  expect(par('publish-caption').value).toBe('Ancienne légende');
  expect(par('publish-remplacer-video')).not.toBeNull();
  const v = par('vte-apercu').querySelector('video');
  Object.defineProperty(v, 'duration', { configurable: true, get: () => 25 });
  Object.defineProperty(v, 'videoWidth', { configurable: true, get: () => 1920 });
  Object.defineProperty(v, 'videoHeight', { configurable: true, get: () => 1080 });
  Object.defineProperty(v, 'readyState', { configurable: true, get: () => 2 });
  v.play = () => Promise.resolve(); v.pause = () => {};
  await act(async () => { v.dispatchEvent(new Event('loadedmetadata')); v.dispatchEvent(new Event('seeked')); await new Promise((r) => setTimeout(r, 30)); });
  expect(par('vte-debut').textContent).toBe('00:00');
  expect(par('vte-fin').textContent).toBe('00:20');
  // La miniature publiée reste prioritaire : l'auto-capture ne la remplace pas.
  expect(par('vte-miniature-apercu').getAttribute('src')).toBe('/api/files/pub/image_mini.jpg');
  await glisser('vte-start', 4);
  await glisser('vte-end', 16);
  expect(par('vte-extrait').textContent).toBe('00:12');
  await act(async () => { par('publish-submit').click(); await new Promise((r) => setTimeout(r, 40)); });
  expect(axios.put).toHaveBeenCalledTimes(1);
  const [url, body] = axios.put.mock.calls[0];
  expect(url).toMatch(/\/publications\/pub-9$/);
  expect(body.trim_start).toBe(4);
  expect(body.trim_end).toBe(16);
  expect(body.caption).toBe('Ancienne légende');
  expect(body.media_url).toBeUndefined();            // pas de réupload
  expect(body.thumbnail_url).toBeUndefined();        // miniature inchangée
});

/**
 * VideoTrimEditor — l'unique éditeur vidéo : aperçu, découpe (poignées + résumé),
 * lecture bornée à l'extrait, scrub, capture de miniature DANS l'extrait.
 * Scénario de référence : vidéo de 21 s, extrait 00:03 → 00:18 = 15 s.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import VideoTrimEditor from '../VideoTrimEditor';

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

let conteneur, racine, props, trims, captures, autos;

function Hote(p) {
  const [trim, setTrim] = React.useState({ start: p.trimStart ?? null, end: p.trimEnd ?? null });
  return (
    <VideoTrimEditor
      videoUrl={p.videoUrl || 'https://x/v.mp4'}
      trimStart={trim.start}
      trimEnd={trim.end}
      aspectRatio={p.aspectRatio || 'auto'}
      thumbnail={p.thumbnail || ''}
      onTrimChange={(t) => { trims.push(t); setTrim(t || { start: null, end: null }); }}
      onThumbnailCapture={(blob, url, t) => captures.push({ blob, url, t })}
      onAutoCapture={p.auto ? (blob, url, t) => autos.push({ blob, url, t }) : undefined}
      onMetadata={(m) => { props.meta = m; }}
    />
  );
}

async function monter(p = {}) {
  props = {}; trims = []; captures = []; autos = [];
  conteneur = document.createElement('div'); document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(<Hote {...p} />); });
  const v = conteneur.querySelector('video');
  v.play = jest.fn(() => { v.dispatchEvent(new Event('play')); return Promise.resolve(); });
  v.pause = jest.fn(() => { v.dispatchEvent(new Event('pause')); });
  return v;
}
async function demonter() { if (racine) await act(async () => { racine.unmount(); }); if (conteneur) conteneur.remove(); }
afterEach(demonter);

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const texte = (id) => (par(id) ? par(id).textContent : '');
async function metadonnees(v, duree, w = 1080, h = 1920) {
  Object.defineProperty(v, 'duration', { configurable: true, get: () => duree });
  Object.defineProperty(v, 'videoWidth', { configurable: true, get: () => w });
  Object.defineProperty(v, 'videoHeight', { configurable: true, get: () => h });
  await act(async () => { v.dispatchEvent(new Event('loadedmetadata')); });
}
async function glisser(id, valeur) {
  const el = par(id);
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  await act(async () => { setter.call(el, String(valeur)); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); });
}
async function cliquer(id) { await act(async () => { par(id).click(); }); }
async function tick(v, t) { v.currentTime = t; await act(async () => { v.dispatchEvent(new Event('timeupdate')); }); }

beforeEach(() => {
  // jsdom n'a pas de toile : on simule une capture JPEG.
  HTMLCanvasElement.prototype.getContext = () => ({ drawImage: () => {} });
  HTMLCanvasElement.prototype.toBlob = function (cb) { cb(new Blob(['jpg'], { type: 'image/jpeg' })); };
  window.URL.createObjectURL = jest.fn(() => 'blob:miniature'); URL.createObjectURL = window.URL.createObjectURL;
  window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
});

test('21 s, extrait 00:03 → 00:18 : résumé, zone surlignée, durée finale 15 s, métadonnées remontées', async () => {
  const v = await monter();
  expect(par('vte-attente')).not.toBeNull();
  await metadonnees(v, 21);
  expect(props.meta).toEqual({ duration: 21, width: 1080, height: 1920 });
  expect(texte('vte-total')).toBe('00:21');
  expect(texte('vte-extrait')).toBe('00:21');
  await glisser('vte-start', 3);
  await glisser('vte-end', 18);
  expect(trims[trims.length - 1]).toEqual({ start: 3, end: 18 });
  expect(texte('vte-debut')).toBe('00:03');
  expect(texte('vte-fin')).toBe('00:18');
  expect(texte('vte-extrait')).toBe('00:15');
  const zone = par('vte-zone');
  expect(zone.style.left).toBe(`${(3 / 21) * 100}%`);
  expect(parseFloat(zone.style.width)).toBeCloseTo((15 / 21) * 100, 3);
  // Le scrub est borné à l'extrait.
  expect(par('vte-scrub').getAttribute('min')).toBe('3');
  expect(par('vte-scrub').getAttribute('max')).toBe('18');
  // Une fin avant le début (< 0,5 s d'extrait) est ignorée.
  const n = trims.length;
  await glisser('vte-end', 3.2);
  expect(trims).toHaveLength(n);
});

test('▶ Lire l’extrait : part à 3 s, s’arrête exactement à 18 s, revient à 3 s ; ↺ Rejouer repart à 3 s ; ⏸ Pause', async () => {
  const v = await monter({ trimStart: 3, trimEnd: 18 });
  await metadonnees(v, 21);
  expect(v.currentTime).toBe(3);                      // positionné au début de l'extrait
  v.currentTime = 0;
  await cliquer('vte-lire');
  expect(v.currentTime).toBe(3);
  expect(v.play).toHaveBeenCalledTimes(1);
  expect(par('vte-pause')).not.toBeNull();            // en lecture : bouton Pause
  await tick(v, 10);
  expect(texte('vte-position')).toBe('00:10 / 00:21');
  await tick(v, 18);
  expect(v.pause).toHaveBeenCalledTimes(1);           // arrêt exact à la fin
  expect(v.currentTime).toBe(3);                      // retour au début de l'extrait
  expect(par('vte-lire')).not.toBeNull();
  await cliquer('vte-rejouer');
  expect(v.currentTime).toBe(3);
  expect(v.play).toHaveBeenCalledTimes(2);
  await cliquer('vte-pause');
  expect(v.pause).toHaveBeenCalledTimes(2);
});

test('scrub à 00:07 dans l’extrait ; capture = la frame affichée (7 s), miniature sélectionnée affichée', async () => {
  const v = await monter({ trimStart: 3, trimEnd: 18 });
  await metadonnees(v, 21);
  Object.defineProperty(v, 'readyState', { configurable: true, get: () => 2 });
  await glisser('vte-scrub', 7);
  expect(v.currentTime).toBe(7);
  await cliquer('vte-capturer');
  await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
  expect(captures).toHaveLength(1);
  expect(captures[0].t).toBe(7);
  expect(captures[0].blob.type).toBe('image/jpeg');
  await demonter();
  await monter({ trimStart: 3, trimEnd: 18, thumbnail: 'blob:miniature' });
  expect(par('vte-miniature-apercu').getAttribute('src')).toBe('blob:miniature');
  expect(texte('vte-capturer')).toBe('Capturer une autre image');
});

test('capture hors extrait → replacée dans l’extrait d’abord (jamais une frame hors séquence)', async () => {
  const v = await monter({ trimStart: 3, trimEnd: 18 });
  await metadonnees(v, 21);
  Object.defineProperty(v, 'readyState', { configurable: true, get: () => 2 });
  v.currentTime = 20;
  await act(async () => { par('vte-capturer').click(); });
  await act(async () => { v.dispatchEvent(new Event('seeked')); await new Promise((r) => setTimeout(r, 30)); });
  expect(captures).toHaveLength(1);
  expect(captures[0].t).toBe(3);
});

test('miniature automatique par défaut (~1 s) une seule fois par vidéo ; Réinitialiser retire la découpe ; ratio 9:16 en aperçu', async () => {
  const v = await monter({ auto: true, aspectRatio: '9:16', trimStart: 3, trimEnd: 18 });
  await metadonnees(v, 21);
  Object.defineProperty(v, 'readyState', { configurable: true, get: () => 2 });
  await act(async () => { v.dispatchEvent(new Event('seeked')); await new Promise((r) => setTimeout(r, 30)); });
  expect(autos).toHaveLength(1);
  await act(async () => { v.dispatchEvent(new Event('loadedmetadata')); v.dispatchEvent(new Event('seeked')); await new Promise((r) => setTimeout(r, 30)); });
  expect(autos).toHaveLength(1);
  expect(par('vte-apercu').getAttribute('data-ratio')).toBe('9:16');
  expect(par('vte-apercu').querySelector('video').style.objectFit).toBe('contain');
  await cliquer('vte-reset');
  expect(trims[trims.length - 1]).toBeNull();
  expect(texte('vte-extrait')).toBe('00:21');
});

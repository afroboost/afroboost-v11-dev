/**
 * V646 — un média de bannière qui ne se charge pas ne laisse jamais une bannière vide.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import BanniereBoutiqueMedia from '../BanniereBoutiqueMedia';

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;
const REPLI = {
  home_shop_banner_url: '/api/files/plateforme.jpg', home_shop_banner_type: 'image',
  home_shop_banner_crop: { x: 0.2, y: 0.3, zoom: 2 },
};
let conteneur; let racine;
const rendre = (props) => act(async () => { racine.render(React.createElement(BanniereBoutiqueMedia, props)); });
const echouer = (s) => act(async () => { conteneur.querySelector(s).dispatchEvent(new Event('error')); });
const media = () => conteneur.querySelector('img, video');

beforeEach(() => {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
});
afterEach(() => { act(() => racine.unmount()); conteneur.remove(); });

test('média valide : aucun repli, cadrage conservé', async () => {
  await rendre({ url: '/api/files/lui.jpg', type: 'image', crop: { x: 0.1, y: 0.1, zoom: 1.5 }, repli: REPLI });
  expect(media().getAttribute('src')).toBe('/api/files/lui.jpg');
  expect(media().style.transform).toContain('1.5');
});

test('vidéo valide : miniature conservée', async () => {
  await rendre({ url: '/api/files/lui.webm', type: 'video', thumbnail: '/api/files/mini.jpg', trimStart: 1, trimEnd: 4, repli: REPLI });
  expect(media().tagName).toBe('VIDEO');
  expect(media().getAttribute('poster')).toBe('/api/files/mini.jpg');
});

test.each([['image', '/api/files/lui.jpg', 'img'], ['vidéo', '/api/files/lui.webm', 'video']])(
  '%s en échec : bannière de la plateforme, avec SON cadrage', async (nom, url, s) => {
    await rendre({ url, type: nom === 'vidéo' ? 'video' : 'image', crop: { x: 0.9, y: 0.9, zoom: 3 }, repli: REPLI });
    await echouer(s);
    expect(media().tagName).toBe('IMG');
    expect(media().getAttribute('src')).toBe('/api/files/plateforme.jpg');
    expect(media().style.transform).toContain('2');
    expect(media().style.transform).not.toContain('3');
  },
);

test('le repli échoue aussi : dégradé, plus aucun chargement', async () => {
  await rendre({ url: '/api/files/lui.jpg', type: 'image', repli: REPLI });
  await echouer('img');
  await echouer('img');
  expect(media()).toBeNull();
  // jsdom rejette ce dégradé (rgba + var) : son rendu réel est mesuré dans parcours_boutique.cjs (V5).
  expect(conteneur.querySelector('.af-boutique-banniere-media')).toBeTruthy();
});

test('sans repli : dégradé, jamais une bannière vide', async () => {
  await rendre({ url: '/api/files/lui.jpg', type: 'image' });
  await echouer('img');
  expect(media()).toBeNull();
  expect(conteneur.querySelector('.af-boutique-banniere-media')).toBeTruthy();
});

test('repli identique au média en échec : pas de boucle', async () => {
  await rendre({ url: '/api/files/plateforme.jpg', type: 'image', repli: REPLI });
  await echouer('img');
  expect(media()).toBeNull();
});

test('un nouveau média repart de zéro', async () => {
  await rendre({ url: '/api/files/a.jpg', type: 'image' });
  await echouer('img');
  await rendre({ url: '/api/files/b.jpg', type: 'image' });
  expect(media().getAttribute('src')).toBe('/api/files/b.jpg');
});

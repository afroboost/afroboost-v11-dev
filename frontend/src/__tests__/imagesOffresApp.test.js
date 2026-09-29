/**
 * IMG-1 — cartes d'offre d'App.js (OfferCard + OfferCardSlider) : une image
 * d'offre en echec ne peut plus generer plus de 2 requetes.
 * Incident mesure sur banc reel : 118 337 requetes en quelques secondes
 * (`onError={(e) => { e.target.src = defaultImage; }}` + picsum bloque).
 * App.js est importe tel quel : son gestionnaire global V416 (capture) est donc
 * actif pendant ces tests, exactement comme en production.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { IMAGE_SECOURS_LOCAL, IMAGE_FINALE } from '../utils/imageSecours';

// Fonctions simples (pas jest.fn) : CRA active `resetMocks`, qui viderait
// leurs implementations avant chaque cas.
jest.mock('axios', () => {
  const ok = (data) => () => Promise.resolve({ data });
  const inst = {
    interceptors: { request: { use: () => 0 }, response: { use: () => 0 } },
    get: ok([]), post: ok({}), put: ok({}), delete: ok({}), patch: ok({}),
    defaults: { headers: { common: {} } },
    isAxiosError: () => false,
  };
  inst.create = () => inst;
  return { __esModule: true, default: inst, ...inst };
});
jest.mock('@/App.css', () => ({}), { virtual: true });
jest.mock('@/lib/utils', () => require('../lib/utils'), { virtual: true });

const { OfferCard, OfferCardSlider } = require('../App');

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;
const desc = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');
let journal = [];
beforeAll(() => {
  Object.defineProperty(HTMLImageElement.prototype, 'src', {
    configurable: true,
    get() { return desc.get.call(this); },
    set(v) { journal.push({ el: this, v }); desc.set.call(this, v); },
  });
});
afterAll(() => { Object.defineProperty(HTMLImageElement.prototype, 'src', desc); });

let conteneur, racine;
beforeEach(() => { journal = []; });
afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
});
async function monter(el) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(el); });
  return conteneur.querySelector('img');
}
const affectations = (img) => journal.filter((j) => j.el === img).map((j) => j.v);
// React 19 pose lui-meme `src` par la propriete : la 1re affectation est donc
// l'image principale. Requete = URL reelle (le GIF V416 et le placeholder
// final sont des `data:`, ils ne sortent pas du navigateur).
const requetes = (img) => affectations(img).filter((u) => u && !String(u).startsWith('data:'));
async function erreur(img, fois = 1) {
  for (let i = 0; i < fois; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await act(async () => { img.dispatchEvent(new Event('error')); });
  }
}

const CAS = [
  ['OfferCard (App)', (offre) => <OfferCard offer={offre} selected={false} onClick={() => {}} />],
  ['OfferCardSlider (App)', (offre) => <OfferCardSlider offer={offre} selected={false} onClick={() => {}} />],
];

describe.each(CAS)('%s', (_nom, rendu) => {
  test('image valide : une seule requete, aucun secours', async () => {
    const img = await monter(rendu({ id: 'o1', name: 'Offre', price: 10, images: ['https://cdn.test/ok.jpg'] }));
    expect(img.getAttribute('src')).toBe('https://cdn.test/ok.jpg');
    expect(requetes(img)).toEqual(['https://cdn.test/ok.jpg']);
    expect(img.getAttribute('data-secours')).toBeNull();
  });

  test('principale 404 -> exactement 1 bascule vers le secours local', async () => {
    const img = await monter(rendu({ id: 'o1', name: 'Offre', price: 10, images: ['https://cdn.test/404.jpg'] }));
    await erreur(img);
    expect(requetes(img)).toEqual(['https://cdn.test/404.jpg', IMAGE_SECOURS_LOCAL]);
  });

  test('principale + secours 404 -> placeholder final puis plus rien', async () => {
    const img = await monter(rendu({ id: 'o1', name: 'Offre', price: 10, images: ['https://cdn.test/404.jpg'] }));
    await erreur(img, 2);
    expect(img.getAttribute('src')).toBe(IMAGE_FINALE);
    const n = affectations(img).length;
    await erreur(img, 3);
    expect(affectations(img)).toHaveLength(n);
  });

  test('offre sans image -> secours local direct (aucun domaine externe, aucun picsum)', async () => {
    const img = await monter(rendu({ id: 'o1', name: 'Offre', price: 10, images: [] }));
    expect(img.getAttribute('src')).toBe(IMAGE_SECOURS_LOCAL);
    await erreur(img, 10);
    expect(requetes(img)).toEqual([IMAGE_SECOURS_LOCAL]);   // le secours n'est pas redemande
    expect(img.getAttribute('src')).toBe(IMAGE_FINALE);
    expect(conteneur.innerHTML).not.toMatch(/picsum|unsplash/);
  });

  test('URL externe bloquee + 10 erreurs -> au plus principale + secours (2 requetes)', async () => {
    const initiale = 'https://picsum.photos/seed/x/400/300';
    const img = await monter(rendu({ id: 'o1', name: 'Offre', price: 10, images: [initiale] }));
    await erreur(img, 10);
    expect(requetes(img)).toEqual([initiale, IMAGE_SECOURS_LOCAL]);
    expect(img.getAttribute('src')).toBe(IMAGE_FINALE);
  });
});

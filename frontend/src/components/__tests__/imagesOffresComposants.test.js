/**
 * IMG-1 — OfferCard.js (OfferCard + OfferCardSlider) et CoachVitrine.js :
 * une image d'offre en echec produit au plus 2 requetes (principale + secours
 * local), puis un placeholder `data:` et plus aucune affectation.
 * Incident mesure sur banc reel : 118 337 requetes en quelques secondes.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { IMAGE_SECOURS_LOCAL, IMAGE_FINALE } from '../../utils/imageSecours';
import { OfferCard, OfferCardSlider } from '../OfferCard';
import CoachVitrine from '../CoachVitrine';

// Fonctions simples (pas jest.fn) : CRA active `resetMocks`.
jest.mock('axios', () => {
  const inst = {
    interceptors: { request: { use: () => 0 }, response: { use: () => 0 } },
    get: (url) => (global.__imgGet ? global.__imgGet(url) : Promise.resolve({ data: {} })),
    post: () => Promise.resolve({ data: {} }),
    put: () => Promise.resolve({ data: {} }),
    delete: () => Promise.resolve({ data: {} }),
    defaults: { headers: { common: {} } },
    isAxiosError: () => false,
  };
  inst.create = () => inst;
  return { __esModule: true, default: inst, ...inst };
});

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
  window.HTMLMediaElement.prototype.play = function () { return Promise.resolve(); };
  window.HTMLMediaElement.prototype.pause = function () {};
  window.scrollTo = () => {};
  if (!window.IntersectionObserver) {
    window.IntersectionObserver = function () { return { observe() {}, unobserve() {}, disconnect() {} }; };
  }
});
afterAll(() => { Object.defineProperty(HTMLImageElement.prototype, 'src', desc); });

let conteneur, racine;
beforeEach(() => { journal = []; global.__imgGet = null; });
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
  await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
}
const affectations = (img) => journal.filter((j) => j.el === img).map((j) => j.v);
// React 19 pose `src` par la propriete : 1re affectation = image principale.
const requetes = (img) => affectations(img).filter((u) => u && !String(u).startsWith('data:'));
async function erreur(img, fois = 1) {
  for (let i = 0; i < fois; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await act(async () => { img.dispatchEvent(new Event('error')); });
  }
}

// --- OfferCard.js ------------------------------------------------------------
const imgCarte = () => conteneur.querySelector('img');
const CARTES = [
  ['OfferCard (components/OfferCard.js)', (o) => <OfferCard offer={o} selected={false} onClick={() => {}} />],
  ['OfferCardSlider (components/OfferCard.js)', (o) => <OfferCardSlider offer={o} selected={false} onClick={() => {}} />],
];

// --- CoachVitrine.js : carte d'offre de la section « Offres disponibles » ----
function vitrine(offres) {
  global.__imgGet = (url) => {
    if (url.indexOf('/coach/vitrine/') !== -1) {
      return Promise.resolve({ data: { coach: { email: 'c@test.ch', username: 'c', name: 'Coach' }, offers: offres, courses: [], concept: {} } });
    }
    return Promise.resolve({ data: [] });
  };
  return <CoachVitrine username="c" onClose={() => {}} onBack={() => {}} />;
}
const imgVitrine = () => [...conteneur.querySelectorAll('img')].find((i) => i.getAttribute('alt') === 'Offre V');

const CAS = [
  ...CARTES.map(([nom, r]) => [nom, (url) => r({ id: 'o1', name: 'Offre V', price: 10, images: url ? [url] : [] }), imgCarte]),
  ['CoachVitrine (carte offre)', (url) => vitrine([{ id: 'o1', name: 'Offre V', price: 10, visible: true, images: url ? [url] : [] }]), imgVitrine],
];

describe.each(CAS)('%s', (_nom, rendu, trouver) => {
  test('image valide : une seule requete, aucun secours', async () => {
    await monter(rendu('https://cdn.test/ok.jpg'));
    const img = trouver();
    expect(img).toBeTruthy();
    expect(requetes(img)).toEqual(['https://cdn.test/ok.jpg']);
    expect(img.getAttribute('data-secours')).toBeNull();
  });

  test('principale 404 -> exactement 1 bascule vers le secours local', async () => {
    await monter(rendu('https://cdn.test/404.jpg'));
    const img = trouver();
    await erreur(img);
    expect(requetes(img)).toEqual(['https://cdn.test/404.jpg', IMAGE_SECOURS_LOCAL]);
  });

  test('principale + secours 404 -> placeholder final, plus aucune affectation', async () => {
    await monter(rendu('https://cdn.test/404.jpg'));
    const img = trouver();
    await erreur(img, 2);
    expect(img.getAttribute('src')).toBe(IMAGE_FINALE);
    const n = affectations(img).length;
    await erreur(img, 5);
    expect(affectations(img)).toHaveLength(n);
  });

  test('URL absente -> secours local direct, jamais de domaine externe', async () => {
    await monter(rendu(''));
    const img = trouver();
    expect(img.getAttribute('src')).toBe(IMAGE_SECOURS_LOCAL);
    await erreur(img, 10);
    expect(requetes(img)).toEqual([IMAGE_SECOURS_LOCAL]);
    expect(conteneur.innerHTML).not.toMatch(/picsum|unsplash/);
  });

  test('URL externe bloquee + 10 erreurs -> 2 requetes maximum', async () => {
    const bloquee = 'https://picsum.photos/seed/bloque/400/300';
    await monter(rendu(bloquee));
    const img = trouver();
    await erreur(img, 10);
    expect(requetes(img)).toEqual([bloquee, IMAGE_SECOURS_LOCAL]);
    expect(img.getAttribute('src')).toBe(IMAGE_FINALE);
  });
});

// --- Garde statique : le motif fautif ne revient dans aucun fichier traite ---
test("aucun onError ne reaffecte directement `src` dans les fichiers d'images traites", () => {
  const fs = require('fs');
  const path = require('path');
  const racineSrc = path.join(__dirname, '..', '..');
  const fichiers = [
    'App.js', 'components/OfferCard.js', 'components/CoachVitrine.js',
    'components/PartnersCarousel.js', 'components/coach/CampaignModal.js',
    'components/dashboard/ConceptEditor.js',
  ];
  const motif = /onError=\{[^}]*\.src\s*=/;
  fichiers.forEach((f) => {
    const texte = fs.readFileSync(path.join(racineSrc, f), 'utf8');
    expect({ f, trouve: motif.test(texte) }).toEqual({ f, trouve: false });
    expect({ f, picsum: /picsum\.photos/.test(texte) }).toEqual({ f, picsum: false });
  });
});

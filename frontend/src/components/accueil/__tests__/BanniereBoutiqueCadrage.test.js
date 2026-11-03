/**
 * V645.4k — CADRAGE DE LA BANNIÈRE BOUTIQUE.
 *
 * Le cadrage n'est jamais « cuit » dans le fichier : il est stocké
 * ({x, y, zoom}) et rejoué à l'affichage. C'est ce qui permet de le modifier
 * indéfiniment, et c'est la seule façon de cadrer une VIDÉO sans la réencoder.
 * Absent, le rendu doit être rigoureusement identique à avant ce lot.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import BanniereBoutiqueMedia from '../BanniereBoutiqueMedia';
import {
  CADRAGE_NEUTRE, cadrageNormalise, cadrageEstNeutre, styleCadrage, ancrageDepuisAire,
} from '../../../utils/banniereCadrage';

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

let conteneur, racine;

async function monter(props) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(<BanniereBoutiqueMedia {...props} />); });
}
afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
});

describe('normalisation du cadrage', () => {
  test('bornes et valeurs illisibles', () => {
    expect(cadrageNormalise({ x: 9, y: -3, zoom: 99 })).toEqual({ x: 1, y: 0, zoom: 3 });
    expect(cadrageNormalise({ x: 'abc', y: null, zoom: undefined })).toEqual(CADRAGE_NEUTRE);
    expect(cadrageNormalise(null)).toEqual(CADRAGE_NEUTRE);
    expect(cadrageNormalise('centre')).toEqual(CADRAGE_NEUTRE);
  });

  test('cadrage neutre reconnu (sert à effacer un cadrage)', () => {
    expect(cadrageEstNeutre(null)).toBe(true);
    expect(cadrageEstNeutre({ x: 0.5, y: 0.5, zoom: 1 })).toBe(true);
    expect(cadrageEstNeutre({ x: 0.2, y: 0.5, zoom: 1 })).toBe(false);
    expect(cadrageEstNeutre({ x: 0.5, y: 0.5, zoom: 1.5 })).toBe(false);
  });

  test('un cadrage neutre ne pose AUCUNE transformation', () => {
    const s = styleCadrage(CADRAGE_NEUTRE);
    expect(s.objectFit).toBe('cover');
    expect(s.objectPosition).toBe('50% 50%');
    expect(s.transform).toBeUndefined();
  });

  test('le zoom part du point d’ancrage, pas du centre', () => {
    const s = styleCadrage({ x: 0.25, y: 0.75, zoom: 2 });
    expect(s.objectPosition).toBe('25% 75%');
    expect(s.transform).toBe('scale(2)');
    expect(s.transformOrigin).toBe('25% 75%');
  });

  test('l’aire en POURCENTAGES de react-easy-crop devient un ancrage', () => {
    // Fenêtre collée en haut à gauche -> ancrage 0/0.
    expect(ancrageDepuisAire({ x: 0, y: 0, width: 50, height: 50 }, 2)).toEqual({ x: 0, y: 0, zoom: 2 });
    // Fenêtre collée en bas à droite -> ancrage 1/1.
    expect(ancrageDepuisAire({ x: 50, y: 50, width: 50, height: 50 }, 2)).toEqual({ x: 1, y: 1, zoom: 2 });
    // Fenêtre pleine largeur : aucun jeu, on reste centré (pas de division par 0).
    expect(ancrageDepuisAire({ x: 0, y: 0, width: 100, height: 100 }, 1)).toEqual(CADRAGE_NEUTRE);
    expect(ancrageDepuisAire(null, 1.5)).toEqual({ x: 0.5, y: 0.5, zoom: 1.5 });
  });
});

describe('rendu de la bannière', () => {
  test('sans cadrage : aucun style inline (rendu d’avant ce lot)', async () => {
    await monter({ url: '/api/files/b.jpg', type: 'image' });
    const img = conteneur.querySelector('img.af-boutique-banniere-media');
    expect(img).not.toBeNull();
    expect(img.getAttribute('style')).toBeNull();
  });

  test('avec cadrage : une IMAGE le respecte', async () => {
    await monter({ url: '/api/files/b.jpg', type: 'image', crop: { x: 0.1, y: 0.9, zoom: 1.8 } });
    const img = conteneur.querySelector('img.af-boutique-banniere-media');
    expect(img.style.objectFit).toBe('cover');
    expect(img.style.objectPosition).toBe('10% 90%');
    expect(img.style.transform).toBe('scale(1.8)');
  });

  test('avec cadrage : une VIDÉO le respecte aussi (aucun réencodage)', async () => {
    await monter({ url: '/api/files/b.mp4', type: 'video', crop: { x: 0.3, y: 0.2, zoom: 1.4 } });
    const v = conteneur.querySelector('video.af-boutique-banniere-media');
    expect(v).not.toBeNull();
    expect(v.style.objectPosition).toBe('30% 20%');
    expect(v.style.transform).toBe('scale(1.4)');
  });

  test('un cadrage corrompu ne casse pas l’affichage', async () => {
    await monter({ url: '/api/files/b.jpg', type: 'image', crop: { x: 'x', y: {}, zoom: -9 } });
    const img = conteneur.querySelector('img.af-boutique-banniere-media');
    expect(img.style.objectPosition).toBe('50% 50%');
    expect(img.style.transform).toBe('');
  });
});

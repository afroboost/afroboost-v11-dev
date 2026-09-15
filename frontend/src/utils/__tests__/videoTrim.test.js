/** DÉCOUPE VIDÉO — règles pures + le hook qui borne un <video>. */
import React, { useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { trimValide, trimDeLOffre, formatTemps, resumeTrim, useTrimVideo } from '../videoTrim';

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

describe('trimValide', () => {
  test('début 3, fin 18 → { 3, 18 } ; extrait de 15 s', () => {
    expect(trimValide(3, 18)).toEqual({ start: 3, end: 18 });
    expect(resumeTrim(20, trimValide(3, 18))).toEqual({ total: '00:20', debut: '00:03', fin: '00:18', extrait: '00:15', secondes: 15 });
  });
  test('absent → null ; fin ≤ début → null ; extrait < 0,5 s → null ; négatif → null', () => {
    expect(trimValide(null, null)).toBeNull();
    expect(trimValide(undefined, undefined)).toBeNull();
    expect(trimValide(10, 5)).toBeNull();
    expect(trimValide(5, 5.2)).toBeNull();
    expect(trimValide(-1, 5)).toEqual({ start: 0, end: 5 }); // début invalide → 0
    expect(trimValide(2, -1)).toBeNull();
  });
  test('fin bornée par la durée réelle ; début au-delà de la durée → null ; début seul → depuis 0', () => {
    expect(trimValide(2, 40, 20)).toEqual({ start: 2, end: 20 });
    expect(trimValide(25, 30, 20)).toBeNull();
    expect(trimValide(null, 8)).toEqual({ start: 0, end: 8 });
    expect(trimValide('2.5', '9.75')).toEqual({ start: 2.5, end: 9.75 });
  });
  test('trimDeLOffre lit les champs de l’offre', () => {
    expect(trimDeLOffre({ video_trim_start: 2, video_trim_end: 17 })).toEqual({ start: 2, end: 17 });
    expect(trimDeLOffre({})).toBeNull();
    expect(trimDeLOffre(null)).toBeNull();
  });
  test('formatTemps', () => {
    expect(formatTemps(0)).toBe('00:00');
    expect(formatTemps(75)).toBe('01:15');
    expect(formatTemps(3723)).toBe('1:02:03');
    expect(resumeTrim(20, null).extrait).toBe('00:20');
  });
});

describe('useTrimVideo — borne la lecture d’un <video>', () => {
  function Lecteur({ trim, loop }) {
    const ref = useRef(null);
    useTrimVideo(ref, trim, { loop });
    return <video ref={ref} data-testid="v" />;
  }
  let conteneur, racine;
  const monter = async (props) => {
    conteneur = document.createElement('div'); document.body.appendChild(conteneur);
    racine = createRoot(conteneur);
    await act(async () => { racine.render(<Lecteur {...props} />); });
    return conteneur.querySelector('video');
  };
  afterEach(async () => { await act(async () => { racine.unmount(); }); conteneur.remove(); });

  test('au chargement des métadonnées, la tête va au début de l’extrait', async () => {
    const v = await monter({ trim: { start: 3, end: 18 } });
    v.currentTime = 0;
    v.dispatchEvent(new Event('loadedmetadata'));
    expect(v.currentTime).toBe(3);
  });
  test('au-delà de la fin : pause + retour au début (sans boucle)', async () => {
    const v = await monter({ trim: { start: 3, end: 18 }, loop: false });
    const pause = jest.fn(); v.pause = pause;
    v.currentTime = 18.2;
    v.dispatchEvent(new Event('timeupdate'));
    expect(pause).toHaveBeenCalledTimes(1);
    expect(v.currentTime).toBe(3);
  });
  test('au-delà de la fin : reboucle sur le début et relance (boucle)', async () => {
    const v = await monter({ trim: { start: 3, end: 18 }, loop: true });
    const play = jest.fn(() => Promise.resolve()); v.play = play;
    v.currentTime = 19;
    v.dispatchEvent(new Event('timeupdate'));
    expect(v.currentTime).toBe(3);
    expect(play).toHaveBeenCalledTimes(1);
  });
  test('lecture lancée hors de l’extrait → repart du début ; dans l’extrait → rien', async () => {
    const v = await monter({ trim: { start: 3, end: 18 } });
    v.currentTime = 0; v.dispatchEvent(new Event('play')); expect(v.currentTime).toBe(3);
    v.currentTime = 10; v.dispatchEvent(new Event('play')); expect(v.currentTime).toBe(10);
    v.currentTime = 10; v.dispatchEvent(new Event('timeupdate')); expect(v.currentTime).toBe(10);
  });
  test('sans découpe : aucun écouteur, le lecteur reste natif', async () => {
    const v = await monter({ trim: null });
    v.currentTime = 50; v.dispatchEvent(new Event('loadedmetadata')); v.dispatchEvent(new Event('timeupdate'));
    expect(v.currentTime).toBe(50);
  });
});

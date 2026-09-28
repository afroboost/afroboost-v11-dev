/**
 * LIVE — PROPRIÉTÉ DE L'IFRAME.
 *
 * `useBoostTribeLive` est instancié plusieurs fois dans la page (barre App.js
 * `barre_app`, modale Publier `publier_modale`). Chaque instance écoute TOUS
 * les postMessage de la fenêtre : l'instance B mémorisait la session de
 * l'iframe de A, et sa croix annonçait la fin d'un Live qui continuait.
 *
 * Règle tenue ici : une instance ne traite QUE les messages dont
 * `event.source` est la fenêtre de SA propre iframe (celle rendue par
 * `<BoostTribeLiveOverlay live={live} />`). Le filtre d'origine reste en place.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import axios from 'axios';

jest.mock('axios', () => ({
  get: jest.fn(),
  post: jest.fn(),
}));

global.IS_REACT_ACT_ENVIRONMENT = true;

const authSession = require('../../../utils/authSession');
const { useBoostTribeLive, BoostTribeLiveOverlay } = require('../BoostTribeLive');

const URL_A = 'https://afroboost.com/live/embed?bt_token=AAA';
const URL_B = 'https://afroboost.com/live/embed?bt_token=BBB';
const CODE = 'AAAA-1111';

// File d'attente des embedUrl renvoyées par /boosttribe/access (une par ouvrir()).
let urlsAcces = [];

beforeEach(() => {
  localStorage.clear();
  urlsAcces = [];
  axios.get.mockReset();
  axios.post.mockReset();
  axios.post.mockImplementation((url) => {
    if (/\/boosttribe\/access$/.test(url)) {
      return Promise.resolve({ data: { embedUrl: urlsAcces.shift(), live: { kind: 'admin' } } });
    }
    return Promise.resolve({ data: { ok: true } });
  });
  jest.spyOn(authSession, 'authValide').mockReturnValue(true);
});

afterEach(() => {
  authSession.authValide.mockRestore();
  document.body.innerHTML = '';
});

/** Les POST /boosttribe/live-status d'un événement donné (corps). */
const annonces = (event) => axios.post.mock.calls
  .filter((c) => /\/boosttribe\/live-status$/.test(c[0]) && c[1] && c[1].event === event)
  .map((c) => c[1]);

/** Un composant = un hook + son overlay, exposé dans `sink[nom]`. */
function Instance({ nom, sink }) {
  const live = useBoostTribeLive(nom);
  sink[nom] = live;
  return <BoostTribeLiveOverlay live={live} />;
}

/** Monte A (et B si demandé) dans le MÊME rendu ; `rendre({avecB})` re-rend. */
function monterPage(avecB) {
  const sink = {};
  const div = document.createElement('div');
  document.body.appendChild(div);
  const root = createRoot(div);
  const rendre = (b) => act(() => {
    root.render(
      <>
        <Instance nom="A" sink={sink} />
        {b ? <Instance nom="B" sink={sink} /> : null}
      </>
    );
  });
  rendre(avecB);
  return { sink, root, rendre };
}

async function ouvrir(sink, nom, url) {
  urlsAcces.push(url);
  await act(async () => { await sink[nom].ouvrir(); });
}

const iframe = (url) => Array.from(document.querySelectorAll('iframe')).find((f) => f.getAttribute('src') === url) || null;

async function envoyer(data, source, origin) {
  const init = { origin: origin || window.location.origin, data };
  if (source !== undefined) init.source = source;
  act(() => { window.dispatchEvent(new MessageEvent('message', init)); });
  await act(async () => {});
}

const started = { type: 'bt:session-started', is_host: true, session_code: CODE };
const heartbeat = { type: 'bt:session-heartbeat', is_host: true, session_code: CODE };
const endedMsg = (reason) => ({ type: 'bt:session-ended', is_host: true, session_code: CODE, reason });

/** Page à deux instances ouvertes, A et B chacune avec son iframe. */
async function deuxOuvertes() {
  const page = monterPage(true);
  await ouvrir(page.sink, 'A', URL_A);
  await ouvrir(page.sink, 'B', URL_B);
  const fa = iframe(URL_A); const fb = iframe(URL_B);
  expect(fa).not.toBeNull();
  expect(fb).not.toBeNull();
  axios.post.mockClear();
  return { ...page, fa, fb };
}

describe('pré-requis jsdom', () => {
  test('une iframe montée par l’overlay a bien un contentWindow utilisable comme source', async () => {
    const { sink, root } = monterPage(false);
    await ouvrir(sink, 'A', URL_A);
    const f = iframe(URL_A);
    expect(f).not.toBeNull();
    expect(f.contentWindow).toBeTruthy();
    expect(f.contentWindow).not.toBe(window);
    const ev = new MessageEvent('message', { origin: window.location.origin, data: {}, source: f.contentWindow });
    expect(ev.source).toBe(f.contentWindow);
    act(() => root.unmount());
  });
});

describe('propriété de l’iframe (une instance ne traite que SON iframe)', () => {
  test('A. une seule instance : started / heartbeat / ended de SON iframe -> 1 POST chacun ; fermer après started -> 1 ended overlay_close', async () => {
    const { sink, root } = monterPage(false);
    await ouvrir(sink, 'A', URL_A);
    const w = iframe(URL_A).contentWindow;
    axios.post.mockClear();

    await envoyer(started, w);
    expect(annonces('started')).toHaveLength(1);
    expect(annonces('started')[0]).toEqual(expect.objectContaining({ event: 'started', session_code: CODE }));
    await envoyer(heartbeat, w);
    expect(annonces('heartbeat')).toHaveLength(1);
    await envoyer(endedMsg('host_leave'), w);
    expect(annonces('ended')).toHaveLength(1);
    expect(annonces('ended')[0].reason).toBe('host_leave');
    expect(sink.A.state).toBe('idle');

    // Nouveau live, puis la croix.
    await ouvrir(sink, 'A', URL_A);
    const w2 = iframe(URL_A).contentWindow;
    axios.post.mockClear();
    await envoyer(started, w2);
    expect(annonces('started')).toHaveLength(1);
    await act(async () => { sink.A.fermer(); });
    const e = annonces('ended');
    expect(e).toHaveLength(1);
    expect(e[0]).toEqual(expect.objectContaining({ session_code: CODE, reason: 'overlay_close' }));
    // `owner`, s'il existe, est le même au début et à la fin.
    if (annonces('started')[0].owner !== undefined) expect(e[0].owner).toBe(annonces('started')[0].owner);
    expect(sink.A.state).toBe('idle');
    act(() => root.unmount());
  });

  test('B. deux instances : started de l’iframe de A -> exactement 1 POST started', async () => {
    const { fa, root } = await deuxOuvertes();
    await envoyer(started, fa.contentWindow);
    expect(annonces('started')).toHaveLength(1);
    act(() => root.unmount());
  });

  test('C. B.fermer() après le started de A -> AUCUN ended ; B idle, A reste live', async () => {
    const { sink, fa, root } = await deuxOuvertes();
    await envoyer(started, fa.contentWindow);
    axios.post.mockClear();
    await act(async () => { sink.B.fermer(); });
    expect(annonces('ended')).toHaveLength(0);
    expect(sink.B.state).toBe('idle');
    expect(sink.A.state).toBe('live');
    expect(iframe(URL_A)).not.toBeNull();
    expect(iframe(URL_B)).toBeNull();
    act(() => root.unmount());
  });

  test('D. A.fermer() -> 1 seul ended au total, même si l’ancienne iframe de A émet ensuite session-ended', async () => {
    const { sink, fa, root } = await deuxOuvertes();
    const ancienne = fa.contentWindow;   // capturée AVANT la fermeture
    await envoyer(started, ancienne);
    axios.post.mockClear();
    await act(async () => { sink.A.fermer(); });
    expect(annonces('ended')).toHaveLength(1);
    expect(annonces('ended')[0].reason).toBe('overlay_close');
    await envoyer(endedMsg('page_unmount'), ancienne);
    expect(annonces('ended')).toHaveLength(1);
    expect(sink.B.state).toBe('live');
    act(() => root.unmount());
  });

  test('E. session-ended host_terminate de l’iframe de A -> 1 ended host_terminate ; A idle, B reste ouvert', async () => {
    const { sink, fa, root } = await deuxOuvertes();
    await envoyer(started, fa.contentWindow);
    axios.post.mockClear();
    await envoyer(endedMsg('host_terminate'), fa.contentWindow);
    const e = annonces('ended');
    expect(e).toHaveLength(1);
    expect(e[0].reason).toBe('host_terminate');
    expect(sink.A.state).toBe('idle');
    expect(sink.B.state).toBe('live');
    expect(iframe(URL_B)).not.toBeNull();
    act(() => root.unmount());
  });

  test('F. heartbeat de l’iframe de A -> exactement 1 POST heartbeat', async () => {
    const { fa, root } = await deuxOuvertes();
    await envoyer(started, fa.contentWindow);
    axios.post.mockClear();
    await envoyer(heartbeat, fa.contentWindow);
    expect(annonces('heartbeat')).toHaveLength(1);
    act(() => root.unmount());
  });

  test('G. démonter B pendant le Live de A -> aucun ended ; heartbeat suivant de A -> 1 POST', async () => {
    const { fa, root, rendre, sink } = await deuxOuvertes();
    await envoyer(started, fa.contentWindow);
    axios.post.mockClear();
    rendre(false);   // B disparaît du rendu
    await act(async () => {});
    expect(annonces('ended')).toHaveLength(0);
    expect(sink.A.state).toBe('live');
    await envoyer(heartbeat, fa.contentWindow);
    expect(annonces('heartbeat')).toHaveLength(1);
    act(() => root.unmount());
  });

  test('H. message sans source, ou d’une fenêtre étrangère (autre iframe, la page elle-même) -> ignoré', async () => {
    const { root } = await deuxOuvertes();
    const intruse = document.createElement('iframe');
    document.body.appendChild(intruse);
    expect(intruse.contentWindow).toBeTruthy();

    await envoyer(started, undefined);
    await envoyer(started, null);
    await envoyer(started, intruse.contentWindow);
    await envoyer(started, window);
    await envoyer(heartbeat, intruse.contentWindow);
    await envoyer(endedMsg('host_terminate'), intruse.contentWindow);
    expect(axios.post).not.toHaveBeenCalled();
    act(() => root.unmount());
  });

  test('I. origine étrangère ignorée, même avec la bonne source', async () => {
    const { fa, root } = await deuxOuvertes();
    await envoyer(started, fa.contentWindow, 'https://evil.invalid');
    await envoyer(heartbeat, fa.contentWindow, 'https://evil.invalid');
    await envoyer(endedMsg('host_terminate'), fa.contentWindow, 'https://evil.invalid');
    expect(axios.post).not.toHaveBeenCalled();
    act(() => root.unmount());
  });
});

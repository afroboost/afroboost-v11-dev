/**
 * LIVE RAPIDE — le bouton « Live » de la barre n'est qu'une PORTE vers le
 * système Live existant. Ces bancs tiennent ce qui fait sa sûreté :
 *
 *  - le rôle n'est PAS décidé dans le navigateur : on n'envoie au serveur que
 *    le code abonné déjà connu (session d'espace, identité chat), jamais une
 *    saisie, et un coach (jeton signé) n'envoie aucun code ;
 *  - un e-mail n'ouvre rien sans preuve : `codes_masked` -> pas de code ;
 *  - les postMessage ne sont acceptés que de boosttribe.pro ou de la page
 *    elle-même (afroboost.com/live) — jamais d'une autre origine ;
 *  - seul le coach (hôte) annonce le live à Afroboost ; un participant, non ;
 *  - « LIVE EN COURS » ne sonde le serveur qu'onglet visible et ne relance
 *    aucun rendu si rien n'a changé (règle CHAT-LOOP).
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import axios from 'axios';

jest.mock('axios', () => ({
  get: jest.fn(),
  post: jest.fn(),
}));

const authSession = require('../../../utils/authSession');

const {
  codeAbonneLocal, emailIdentiteLocale, resoudreCodeAbonne,
  useBoostTribeLive, useLiveEnCours, BoostTribeLiveOverlay, EVENEMENT_LIVE,
} = require('../BoostTribeLive');

beforeEach(() => {
  localStorage.clear();
  axios.get.mockReset();
  axios.post.mockReset();
});

describe('identité locale (aucune saisie, aucun réseau)', () => {
  test('la session d’espace abonné donne le code', () => {
    localStorage.setItem('afroboost_espace_token', JSON.stringify({ token: 'x'.repeat(20), code: 'AFR-TEST01', expires_at: '2099-01-01T00:00:00Z' }));
    expect(codeAbonneLocal()).toBe('AFR-TEST01');
  });
  test('une session expirée ne vaut rien', () => {
    localStorage.setItem('afroboost_espace_token', JSON.stringify({ token: 'x'.repeat(20), code: 'AFR-TEST01', expires_at: '2000-01-01T00:00:00Z' }));
    expect(codeAbonneLocal()).toBe('');
  });
  test('l’identité chat donne le code, jamais un e-mail à la place', () => {
    localStorage.setItem('afroboost_identity', JSON.stringify({ email: 'p@exemple.invalid', code: 'p@exemple.invalid' }));
    expect(codeAbonneLocal()).toBe('');
    expect(emailIdentiteLocale()).toBe('p@exemple.invalid');
  });
});

describe('resoudreCodeAbonne', () => {
  test('code local -> aucun appel réseau', async () => {
    localStorage.setItem('afroboost_identity', JSON.stringify({ code: 'AFR-LOCAL1' }));
    await expect(resoudreCodeAbonne()).resolves.toBe('AFR-LOCAL1');
    expect(axios.get).not.toHaveBeenCalled();
  });
  test('e-mail identifié -> même endpoint que « Publier », dédoublonné par code', async () => {
    localStorage.setItem('afroboost_identity', JSON.stringify({ email: 'p@exemple.invalid' }));
    axios.get.mockResolvedValue({ data: { subscriptions: [{ code: 'afr-a' }, { code: 'AFR-A' }, { code: 'AFR-B' }] } });
    await expect(resoudreCodeAbonne()).resolves.toBe('afr-a');
    expect(axios.get).toHaveBeenCalledWith(expect.stringMatching(/\/discount-codes\/subscriptions\/status$/), { params: { email: 'p@exemple.invalid' } });
  });
  test('codes masqués (V296, aucune preuve d’appareil) -> aucun code', async () => {
    localStorage.setItem('afroboost_identity', JSON.stringify({ email: 'p@exemple.invalid' }));
    axios.get.mockResolvedValue({ data: { codes_masked: true, subscriptions: [{ code: 'AFR-X' }] } });
    await expect(resoudreCodeAbonne()).resolves.toBe('');
  });
  test('personne d’identifié -> aucun code, aucun réseau', async () => {
    await expect(resoudreCodeAbonne()).resolves.toBe('');
    expect(axios.get).not.toHaveBeenCalled();
  });
});

function monter(Composant) {
  const div = document.createElement('div');
  document.body.appendChild(div);
  const root = createRoot(div);
  act(() => { root.render(<Composant />); });
  return { div, root };
}

describe('useBoostTribeLive', () => {
  test('ouvrir : le code abonné part dans le CORPS, jamais en query ; un e-mail ne part pas', async () => {
    let live;
    const C = () => { live = useBoostTribeLive(); return null; };
    monter(C);
    axios.post.mockResolvedValue({ data: { embedUrl: 'https://afroboost.com/live/embed?bt_token=t', live: { kind: 'subscriber' } } });
    await act(async () => { await live.ouvrir({ subscriberCode: 'AFR-OK' }); });
    expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/boosttribe\/access$/), { subscriber_code: 'AFR-OK' });
    expect(live.state).toBe('live');
    await act(async () => { await live.ouvrir({ subscriberCode: 'p@exemple.invalid' }); });
    expect(axios.post).toHaveBeenLastCalledWith(expect.any(String), {});
  });

  test('refus serveur -> denied avec le motif, aucun overlay', async () => {
    let live;
    const C = () => { live = useBoostTribeLive(); return <BoostTribeLiveOverlay live={live} />; };
    monter(C);
    axios.post.mockRejectedValue({ response: { status: 403, data: { reason: 'no_credit' } } });
    let r;
    await act(async () => { r = await live.ouvrir({ subscriberCode: 'AFR-VIDE' }); });
    expect(r).toEqual({ ok: false, reason: 'no_credit' });
    expect(live.state).toBe('denied');
    expect(document.querySelector('iframe[title="BoostTribe live"]')).toBeNull();
  });

  test('postMessage : origine étrangère ignorée ; hôte -> annonce started ; participant -> rien', async () => {
    jest.spyOn(authSession, 'authValide').mockReturnValue(true);
    let live;
    const C = () => { live = useBoostTribeLive(); return null; };
    monter(C);
    axios.post.mockResolvedValue({ data: { ok: true } });
    const envoyer = (origin, data) => act(() => { window.dispatchEvent(new MessageEvent('message', { origin, data })); });
    envoyer('https://evil.invalid', { type: 'bt:session-started', is_host: true, session_code: 'AAAA-1111' });
    expect(axios.post).not.toHaveBeenCalled();
    envoyer(window.location.origin, { type: 'bt:session-started', is_host: false, session_code: 'AAAA-1111' });
    expect(axios.post).not.toHaveBeenCalled();
    envoyer('https://boosttribe.pro', { type: 'bt:session-started', is_host: true, session_code: 'AAAA-1111' });
    await act(async () => {});
    expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/boosttribe\/live-status$/), { event: 'started', session_code: 'AAAA-1111' });
    envoyer(window.location.origin, { type: 'bt:session-ended', is_host: true, session_code: 'AAAA-1111' });
    await act(async () => {});
    expect(axios.post).toHaveBeenLastCalledWith(expect.any(String), { event: 'ended', session_code: 'AAAA-1111' });
    authSession.authValide.mockRestore();
  });

  test('sans jeton coach signé, aucune annonce ne part (un participant ne peut pas déclarer un live)', async () => {
    jest.spyOn(authSession, 'authValide').mockReturnValue(false);
    let live;
    const C = () => { live = useBoostTribeLive(); return null; };
    monter(C);
    act(() => { window.dispatchEvent(new MessageEvent('message', { origin: 'https://boosttribe.pro', data: { type: 'bt:session-started', is_host: true, session_code: 'AAAA-1111' } })); });
    await act(async () => {});
    expect(axios.post).not.toHaveBeenCalled();
    authSession.authValide.mockRestore();
  });
});

describe('useLiveEnCours', () => {
  test('sonde onglet visible, reflète le serveur, réagit à l’annonce locale', async () => {
    jest.useFakeTimers();
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
    axios.get.mockResolvedValue({ data: { active: true } });
    let actif;
    const C = () => { actif = useLiveEnCours(1000); return null; };
    monter(C);
    await act(async () => {});
    expect(actif).toBe(true);
    expect(axios.get).toHaveBeenCalledWith(expect.stringMatching(/\/boosttribe\/live-status$/));
    act(() => { window.dispatchEvent(new CustomEvent(EVENEMENT_LIVE, { detail: { active: false } })); });
    expect(actif).toBe(false);
    // Onglet caché : la sonde ne part plus.
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    axios.get.mockClear();
    act(() => { jest.advanceTimersByTime(3000); });
    expect(axios.get).not.toHaveBeenCalled();
    jest.useRealTimers();
  });
});

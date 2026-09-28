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
    expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/boosttribe\/live-status$/),
      expect.objectContaining({ event: 'started', session_code: 'AAAA-1111' }), expect.any(Object));
    envoyer(window.location.origin, { type: 'bt:session-ended', is_host: true, session_code: 'AAAA-1111' });
    await act(async () => {});
    expect(axios.post).toHaveBeenLastCalledWith(expect.any(String),
      expect.objectContaining({ event: 'ended', session_code: 'AAAA-1111' }), expect.any(Object));
    authSession.authValide.mockRestore();
  });

  // ═══ BATTEMENT DE CŒUR — le relais du seul départ sans événement ═══════════
  //
  //  Quand la connexion du coach tombe et que l'onglet reste ouvert, aucun
  //  événement navigateur ne se produit : le live restait public trois heures.
  //  Sa page redit « je suis là » ; ce relais transmet, et rien de plus.
  test('battement : relayé au serveur, mais il ne touche PAS l’affichage du badge', async () => {
    jest.spyOn(authSession, 'authValide').mockReturnValue(true);
    const C = () => { useBoostTribeLive(); return null; };
    monter(C);
    axios.post.mockResolvedValue({ data: { ok: true } });
    const vus = [];
    const espion = (e) => vus.push(!!(e.detail && e.detail.active));
    window.addEventListener('afroboost:live-status', espion);
    const envoyer = (origin, data) => act(() => { window.dispatchEvent(new MessageEvent('message', { origin, data })); });

    envoyer(window.location.origin, { type: 'bt:session-heartbeat', is_host: true, session_code: 'AAAA-1111' });
    await act(async () => {});
    // V553 : le corps du battement est INCHANGÉ (ni reason ni source) ; seul un X-Request-ID s'ajoute.
    expect(axios.post).toHaveBeenLastCalledWith(expect.stringMatching(/\/boosttribe\/live-status$/),
      { event: 'heartbeat', session_code: 'AAAA-1111' },
      { headers: { 'X-Request-ID': expect.any(String) } });
    // Un battement ne change RIEN à l'écran : il ne doit pas réveiller le badge.
    expect(vus).toEqual([]);

    window.removeEventListener('afroboost:live-status', espion);
    authSession.authValide.mockRestore();
  });

  test('battement : un participant ou une origine étrangère n’en émet aucun', async () => {
    jest.spyOn(authSession, 'authValide').mockReturnValue(true);
    const C = () => { useBoostTribeLive(); return null; };
    monter(C);
    axios.post.mockResolvedValue({ data: { ok: true } });
    const envoyer = (origin, data) => act(() => { window.dispatchEvent(new MessageEvent('message', { origin, data })); });
    envoyer('https://evil.invalid', { type: 'bt:session-heartbeat', is_host: true, session_code: 'AAAA-1111' });
    envoyer(window.location.origin, { type: 'bt:session-heartbeat', is_host: false, session_code: 'AAAA-1111' });
    envoyer(window.location.origin, { type: 'bt:session-heartbeat', is_host: true });
    await act(async () => {});
    expect(axios.post).not.toHaveBeenCalled();
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

// ═══ V553 — OBSERVABILITÉ DES FINS DE LIVE ═════════════════════════════════
describe('V553 : chaque fin annoncée dit POURQUOI et D’OÙ', () => {
  const envoyer = (data) => act(() => {
    window.dispatchEvent(new MessageEvent('message', { origin: window.location.origin, data }));
  });
  const monterInstance = (nom, sink) => {
    const C = () => { sink.live = useBoostTribeLive(nom); return null; };
    return monter(C);
  };
  // Les bancs précédents laissent des instances montées (nom `inconnu`) qui
  // écoutent aussi : on ne regarde que les instances nommées de ce bloc.
  const corpsEnded = () => axios.post.mock.calls
    .filter((c) => c[1] && c[1].event === 'ended' && !/:inconnu:/.test(c[1].source || ''))
    .map((c) => c[1]);

  beforeEach(() => { jest.spyOn(authSession, 'authValide').mockReturnValue(true); axios.post.mockResolvedValue({ data: { ok: true } }); });
  afterEach(() => { authSession.authValide.mockRestore(); });

  test('motifIframe : liste blanche recopiée, inconnu -> unknown, absent -> iframe_ended_sans_motif', () => {
    const { motifIframe } = require('../BoostTribeLive');
    ['host_terminate', 'host_leave', 'page_unmount', 'consume_refused', 'unknown']
      .forEach((m) => expect(motifIframe({ reason: m })).toBe(m));
    expect(motifIframe({ reason: 'overlay_close' })).toBe('unknown');   // l'iframe ne peut pas se faire passer pour la croix
    expect(motifIframe({ reason: '<script>' })).toBe('unknown');
    expect(motifIframe({})).toBe('iframe_ended_sans_motif');
  });

  test('le relais recopie le motif de l’iframe et nomme son instance', async () => {
    const s = {};
    const { root } = monterInstance('barre_app', s);
    axios.post.mockClear();
    envoyer({ type: 'bt:session-ended', is_host: true, session_code: 'AAAA-1111', reason: 'host_terminate' });
    await act(async () => {});
    const c = corpsEnded();
    expect(c).toHaveLength(1);
    expect(c[0].reason).toBe('host_terminate');
    expect(c[0].source).toMatch(/^iframe:barre_app:/);
    const appel = axios.post.mock.calls.find((x) => x[1] && x[1].source === c[0].source);
    expect(appel[2].headers['X-Request-ID']).toEqual(expect.any(String));
    act(() => root.unmount());
  });

  test('ancien bundle sans reason -> iframe_ended_sans_motif', async () => {
    const s = {};
    const { root } = monterInstance('barre_app', s);
    axios.post.mockClear();
    envoyer({ type: 'bt:session-ended', is_host: true, session_code: 'AAAA-1111' });
    await act(async () => {});
    expect(corpsEnded()[0].reason).toBe('iframe_ended_sans_motif');
    act(() => root.unmount());
  });

  test('fermer(origine) -> overlay_close avec l’origine ; un événement React est ignoré', async () => {
    const s = {};
    const { root } = monterInstance('publier_modale', s);
    envoyer({ type: 'bt:session-started', is_host: true, session_code: 'AAAA-1111' });
    await act(async () => {});
    axios.post.mockClear();
    await act(async () => { s.live.fermer('croix_test'); });
    let c = corpsEnded();
    expect(c).toHaveLength(1);
    expect(c[0]).toEqual(expect.objectContaining({ event: 'ended', session_code: 'AAAA-1111', reason: 'overlay_close' }));
    expect(c[0].source).toMatch(/^overlay:croix_test:/);
    // Sans origine (ou avec un événement de clic) : c'est le nom de l'instance qui part.
    envoyer({ type: 'bt:session-started', is_host: true, session_code: 'AAAA-1111' });
    await act(async () => {});
    axios.post.mockClear();
    await act(async () => { s.live.fermer({ type: 'click' }); });
    c = corpsEnded();
    expect(c[0].source).toMatch(/^overlay:publier_modale:/);
    act(() => root.unmount());
  });

  test('DEUX instances montées : un seul message de l’iframe produit DEUX annonces (cause probable des fins fantômes)', async () => {
    const a = {}; const b = {};
    const ra = monterInstance('barre_app', a);
    const rb = monterInstance('publier_modale', b);
    axios.post.mockClear();
    envoyer({ type: 'bt:session-started', is_host: true, session_code: 'AAAA-1111' });
    await act(async () => {});
    const sources = axios.post.mock.calls
      .filter((x) => x[1] && x[1].event === 'started' && !/:inconnu:/.test(x[1].source || ''))
      .map((x) => x[1].source.split(':')[1]).sort();
    expect(sources).toEqual(['barre_app', 'publier_modale']);   // les DEUX instances ont mémorisé le code
    axios.post.mockClear();
    // La croix de l'instance B (dont l'overlay n'est même pas celui de l'iframe) termine le live.
    await act(async () => { b.live.fermer(); });
    const c = corpsEnded();
    expect(c).toHaveLength(1);
    expect(c[0].source).toMatch(/^overlay:publier_modale:/);
    act(() => { ra.root.unmount(); rb.root.unmount(); });
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

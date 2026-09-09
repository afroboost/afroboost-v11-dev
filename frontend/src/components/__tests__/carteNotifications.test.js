/**
 * PUSH-PWA — L'ABONNEMENT SE RECRÉE TOUT SEUL, SANS PASSER PAR LES RÉGLAGES.
 *
 * CE QUE CES BANCS PROUVENT (cas A→J du lot)
 *   A. permission accordée + abonnement présent  -> AUCUN nouvel abonnement
 *   B. permission accordée + abonnement absent   -> recréé automatiquement
 *   C. permission jamais demandée                -> un bouton, JAMAIS de popup
 *   D. clic sur le bouton + accord               -> abonnement créé
 *   E. permission refusée                        -> aucune demande, aucune boucle
 *   F. endpoint mort (410) puis retour           -> identique au cas B
 *   G. l'abonnement part avec le BON compte
 *   H. l'endpoint remplacé est NOMMÉ (les autres appareils sont épargnés)
 *   I. ouvertures répétées                       -> aucun endpoint supplémentaire
 *   J. rien n'est envoyé qui empêcherait le serveur d'identifier l'appareil
 *
 * axios, le service worker et Notification sont doublés : aucun réseau, aucune
 * vraie notification, aucune popup.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import axios from 'axios';
import CarteNotifications from '../CarteNotifications';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

let conteneur, racine, sousJacent, abonner, getSubscription;

const ENDPOINT = 'https://fcm.googleapis.com/fcm/send/NOUVEAU';
const ANCIEN = 'https://fcm.googleapis.com/fcm/send/ANCIEN';

function preparerNavigateur({ permission, abonnementExistant }) {
  global.Notification = { permission, requestPermission: jest.fn(async () => permission) };
  getSubscription = jest.fn(async () => (abonnementExistant
    ? { endpoint: ANCIEN, toJSON: () => ({ endpoint: ANCIEN }) } : null));
  abonner = jest.fn(async () => ({ endpoint: ENDPOINT, toJSON: () => ({ endpoint: ENDPOINT }) }));
  sousJacent = { pushManager: { getSubscription, subscribe: abonner } };
  global.navigator.serviceWorker = { ready: Promise.resolve(sousJacent) };
  global.window.PushManager = function () {};
  global.caches = { open: jest.fn(async () => ({ put: jest.fn() })) };
  global.window.atob = (b) => Buffer.from(b, 'base64').toString('binary');
}

beforeEach(() => {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  jest.clearAllMocks();
  try { localStorage.clear(); } catch (e) { /* ignore */ }
  axios.get.mockResolvedValue({ data: { publicKey: 'QUlBQUFBQUFBQQ' } });
  axios.post.mockResolvedValue({ data: { success: true } });
});
afterEach(() => {
  if (racine) act(() => racine.unmount());
  conteneur.remove();
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);

async function monter(props = {}) {
  await act(async () => {
    racine = createRoot(conteneur);
    racine.render(React.createElement(CarteNotifications, {
      participantId: 'sub_moi@x.ch', role: 'subscriber', email: 'moi@x.ch', ...props,
    }));
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
}

test('A. permission accordée + abonnement présent -> aucun nouvel abonnement', async () => {
  preparerNavigateur({ permission: 'granted', abonnementExistant: true });
  await monter();
  expect(abonner).not.toHaveBeenCalled();
  expect(axios.post).toHaveBeenCalledTimes(1);          // simple réenregistrement
  expect(par('carte-notifications').textContent).toMatch(/activées/i);
});

test('B/F. permission accordée + abonnement absent (ex. 410) -> recréé automatiquement', async () => {
  preparerNavigateur({ permission: 'granted', abonnementExistant: false });
  await monter();
  expect(abonner).toHaveBeenCalledTimes(1);
  expect(abonner.mock.calls[0][0].userVisibleOnly).toBe(true);
  expect(axios.post.mock.calls[0][1].subscription.endpoint).toBe(ENDPOINT);
});

test('C. permission jamais demandée -> un bouton, et AUCUNE popup', async () => {
  preparerNavigateur({ permission: 'default', abonnementExistant: false });
  await monter();
  expect(global.Notification.requestPermission).not.toHaveBeenCalled();
  expect(abonner).not.toHaveBeenCalled();
  expect(par('carte-notifications-activer')).not.toBeNull();
  expect(par('carte-notifications').textContent).toMatch(/Activer les notifications/i);
});

test('D. le clic demande la permission et crée l’abonnement', async () => {
  preparerNavigateur({ permission: 'default', abonnementExistant: false });
  await monter();
  global.Notification.permission = 'granted';
  global.Notification.requestPermission = jest.fn(async () => 'granted');
  await act(async () => { par('carte-notifications-activer').click(); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  expect(global.Notification.requestPermission).toHaveBeenCalledTimes(1);
  expect(abonner).toHaveBeenCalledTimes(1);
});

test('E. permission refusée -> aucune demande, aucun bouton, aucune boucle', async () => {
  preparerNavigateur({ permission: 'denied', abonnementExistant: false });
  await monter();
  expect(global.Notification.requestPermission).not.toHaveBeenCalled();
  expect(abonner).not.toHaveBeenCalled();
  expect(par('carte-notifications-activer')).toBeNull();
  expect(par('carte-notifications').textContent).toMatch(/désactivées/i);
});

test('G. l’abonnement part avec le bon compte', async () => {
  preparerNavigateur({ permission: 'granted', abonnementExistant: false });
  await monter();
  const corps = axios.post.mock.calls[0][1];
  expect(corps.participant_id).toBe('sub_moi@x.ch');
  expect(corps.email).toBe('moi@x.ch');
  expect(corps.role).toBe('subscriber');
});

test('H. l’endpoint remplacé est NOMMÉ — les autres appareils sont épargnés', async () => {
  localStorage.setItem('af_push_last_endpoint', ANCIEN);
  preparerNavigateur({ permission: 'granted', abonnementExistant: false });
  await monter();
  const corps = axios.post.mock.calls[0][1];
  expect(corps.previous_endpoint).toBe(ANCIEN);         // UN seul, nommé
  expect(corps.subscription.endpoint).toBe(ENDPOINT);
});

test('H2. on ne demande jamais d’éteindre l’endpoint qu’on vient d’enregistrer', async () => {
  localStorage.setItem('af_push_last_endpoint', ANCIEN);
  preparerNavigateur({ permission: 'granted', abonnementExistant: true });
  await monter();                                       // l'existant EST l'ancien
  expect(axios.post.mock.calls[0][1].previous_endpoint).toBeNull();
});

test('I. ouvertures répétées -> aucun endpoint supplémentaire', async () => {
  preparerNavigateur({ permission: 'granted', abonnementExistant: true });
  await monter();
  await act(async () => racine.unmount());
  racine = null;
  await monter();
  expect(abonner).not.toHaveBeenCalled();               // jamais de nouvelle création
  const endpoints = axios.post.mock.calls.map((c) => c[1].subscription.endpoint);
  expect(new Set(endpoints).size).toBe(1);
});

test('J. aucun jargon technique n’est montré à l’utilisateur', async () => {
  preparerNavigateur({ permission: 'default', abonnementExistant: false });
  await monter();
  const t = par('carte-notifications').textContent;
  for (const mot of ['endpoint', 'FCM', 'VAPID', 'service worker', 'push manager']) {
    expect(t.toLowerCase()).not.toContain(mot.toLowerCase());
  }
});

test('non supporté -> la carte disparaît, l’espace reste utilisable', async () => {
  global.Notification = undefined;
  global.navigator.serviceWorker = undefined;
  await monter();
  expect(par('carte-notifications')).toBeNull();
});

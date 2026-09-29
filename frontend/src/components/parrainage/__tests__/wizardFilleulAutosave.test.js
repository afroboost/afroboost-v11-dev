/**
 * UX-P2 — WizardFilleul, étape 2 : aperçu immédiat + enregistrement automatique.
 *
 * axios mocké (aucun réseau), minuteurs simulés (debounce 500 ms). Le contrat
 * serveur est celui de l'agent serveur UX-P2 : PATCH /chain (photo_url,
 * whatsapp, consent_contact) et POST /chain/photo (multipart `file`).
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import InvitationDuo from '../InvitationDuo';
import { MESSAGE_CHAINE_DEFAUT, _resetParrainagePourTest, numeroWhatsAppChaine } from '../../../utils/parrainage';
import { TEXTE_CONSENT_CONTACT } from '../WizardFilleul';

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), patch: jest.fn(), delete: jest.fn() },
}));
jest.mock('qrcode.react', () => ({
  QRCodeSVG: (p) => <svg data-testid="qr-svg" data-value={p.value} />,
  QRCodeCanvas: (p) => <canvas data-testid="qr-canvas" data-value={p.value} />,
}));

let conteneur, racine;
const fetchOrigine = global.fetch;
beforeEach(() => {
  jest.useFakeTimers();
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  jest.clearAllMocks();
  axios.get.mockReset(); axios.post.mockReset(); axios.patch.mockReset();
  window.localStorage.clear();
  _resetParrainagePourTest();
  global.fetch = undefined;
  window.open = jest.fn(() => null);
  delete navigator.share; delete navigator.canShare;
  Object.defineProperty(navigator, 'clipboard', { value: { writeText: jest.fn(() => Promise.resolve()) }, configurable: true });
});
afterEach(() => {
  if (racine) act(() => racine.unmount());
  racine = null;
  conteneur.remove();
  global.fetch = fetchOrigine;
  jest.useRealTimers();
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const vider = () => act(async () => { for (let i = 0; i < 15; i += 1) await Promise.resolve(); });
async function monter(element) {
  await act(async () => { racine = createRoot(conteneur); racine.render(element); });
  await vider();
}
const cliquer = async (id) => { await act(async () => { par(id).click(); }); await vider(); };
const attendre = async (ms) => { await act(async () => { jest.advanceTimersByTime(ms); }); await vider(); };
const saisir = async (id, v) => {
  await act(async () => {
    const el = par(id);
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(el, v);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
};

const COURSE = { id: 'c1', name: 'Afroboost Dimanche', time: '18:30', locationName: 'Bord du Lac, Auvernier' };
const OCC = '2026-09-27T18:30:00';
const PUB = { status: 'waiting', sponsor_first_name: 'Bassi', course: COURSE, occurrence: OCC, expired: false, version: 1,
  chain_required: true, chain: { exists: false, shared: false } };
const CHILD = (v, extra) => Object.assign({
  share_token: 'T1', share_url: `https://afroboost.com/api/share/duo/T1?v=${v}`,
  invite_url: 'https://afroboost.com/duo/T1', card_url: `https://afroboost.com/api/share/duo/T1/carte.jpg?v=${v}`,
  display_name: null, message: MESSAGE_CHAINE_DEFAUT, course: COURSE, occurrence: OCC,
  inviter_display: { prenom: null, photo_url: null },
}, extra || {});
const PREVIEW_OK = { ok: true, fallback: false, checks: {} };

function routerPost({ enfant, photo } = {}) {
  axios.post.mockImplementation((url) => {
    const u = String(url);
    if (u.endsWith('/chain')) return Promise.resolve({ status: 201, data: { child: enfant || CHILD(3), edit_key: 'K1', shared: false, preview: PREVIEW_OK } });
    if (u.endsWith('/chain/photo')) return photo ? photo() : Promise.resolve({ data: { photo_url: '/api/files/p1.jpg' } });
    if (u.endsWith('/chain/share')) return Promise.resolve({ data: { shared: true, child: CHILD(9) } });
    if (u.endsWith('/join')) return Promise.resolve({ data: { status: 'friend_registered', tickets: [] } });
    return Promise.reject(new Error(`inattendu ${u}`));
  });
}
const patchOk = (v) => axios.patch.mockImplementation((url, corps) => Promise.resolve({
  data: { child: CHILD(v, { display_name: corps.display_name || null, inviter_display: { prenom: corps.display_name || null, photo_url: corps.photo_url || null } }), preview: PREVIEW_OK },
}));
const postsVers = (fin) => axios.post.mock.calls.filter((c) => String(c[0]).endsWith(fin));

async function entrerEtape2(opts) {
  routerPost(opts);
  axios.get.mockResolvedValue({ data: PUB });
  await monter(<InvitationDuo token="T0" />);
  await cliquer('wf-continuer');
}

describe('UX-P2 — WizardFilleul : aperçu immédiat + enregistrement automatique', () => {
  test('plus de bouton « Mettre à jour ma carte » ; prénom → aperçu IMMÉDIAT puis UN PATCH après 500 ms', async () => {
    patchOk(5);
    await entrerEtape2();
    expect(par('wf-mettre-a-jour')).toBeNull();
    expect(conteneur.textContent).not.toContain('Mettre à jour ma carte');
    await saisir('wf-nom', 'Henri');
    expect(par('bandeau-texte').textContent).toBe('Henri t’invite à découvrir Afroboost');
    await attendre(499);
    expect(axios.patch).not.toHaveBeenCalled();
    await attendre(1);
    expect(axios.patch).toHaveBeenCalledTimes(1);
    expect(axios.patch.mock.calls[0][1]).toEqual({ display_name: 'Henri', message: MESSAGE_CHAINE_DEFAUT });
    expect(axios.patch.mock.calls[0][2].headers).toEqual({ 'X-Chain-Key': 'K1' });
    expect(par('wf-statut').textContent).toBe('Enregistré');
    expect(par('wf-carte').querySelector('img').getAttribute('src')).toContain('carte.jpg?v=5');
    await attendre(2000);
    expect(axios.patch).toHaveBeenCalledTimes(1); // rien ne change → aucun autre appel
  });

  test('frappe rapide → un seul PATCH, avec la valeur finale', async () => {
    patchOk(5);
    await entrerEtape2();
    for (const v of ['H', 'He', 'Hen', 'Henr', 'Henri']) {
      await saisir('wf-nom', v);
      await attendre(200);
    }
    expect(axios.patch).not.toHaveBeenCalled();
    await attendre(500);
    expect(axios.patch).toHaveBeenCalledTimes(1);
    expect(axios.patch.mock.calls[0][1].display_name).toBe('Henri');
  });

  test('« Enregistrement… » pendant le PATCH', async () => {
    let resoudre;
    axios.patch.mockImplementation(() => new Promise((r) => { resoudre = r; }));
    await entrerEtape2();
    await saisir('wf-nom', 'Awa');
    await attendre(500);
    expect(par('wf-statut').textContent).toBe('Enregistrement…');
    await act(async () => { resoudre({ data: { child: CHILD(5, { display_name: 'Awa' }), preview: PREVIEW_OK } }); });
    await vider();
    expect(par('wf-statut').textContent).toBe('Enregistré');
  });

  test('WhatsApp avec modif en attente : fenêtre ouverte dans le geste, PATCH d’abord, puis le share_url RENVOYÉ', async () => {
    patchOk(7);
    const fen = { location: { href: '' }, close: jest.fn() };
    window.open = jest.fn(() => fen);
    await entrerEtape2();
    await saisir('wf-nom', 'Henri');
    await cliquer('wf-whatsapp'); // avant les 500 ms : flush
    expect(window.open).toHaveBeenCalledTimes(1);
    expect(window.open.mock.calls[0][0]).toBe(''); // synchrone, vide
    expect(fen.opener).toBeNull();
    expect(axios.patch).toHaveBeenCalledTimes(1);
    const lien = decodeURIComponent(fen.location.href);
    expect(lien).toContain('https://afroboost.com/api/share/duo/T1?v=7');
    expect(lien).not.toContain('?v=3');
    // l'enregistrement du partage vient APRÈS le PATCH
    const ordrePatch = axios.patch.mock.invocationCallOrder[0];
    const share = axios.post.mock.calls.findIndex((c) => String(c[0]).endsWith('/chain/share'));
    expect(axios.post.mock.invocationCallOrder[share]).toBeGreaterThan(ordrePatch);
    await attendre(2000);
    expect(axios.patch).toHaveBeenCalledTimes(1); // le minuteur a été annulé
  });

  test('WhatsApp avec modif en attente et fenêtre refusée → « touche encore », jamais l’ancienne URL', async () => {
    patchOk(7);
    await entrerEtape2();
    await saisir('wf-nom', 'Henri');
    await cliquer('wf-whatsapp');
    expect(axios.patch).toHaveBeenCalledTimes(1);
    expect(postsVers('/chain/share').length).toBe(0);
    expect(par('wf-info').textContent).toContain('Touche encore WhatsApp');
    await cliquer('wf-whatsapp'); // plus rien en attente : ouverture synchrone directe
    expect(decodeURIComponent(String(window.open.mock.calls[1][0]))).toContain('?v=7');
  });

  test('Copier le lien avec modif en attente → PATCH puis copie du share_url renvoyé', async () => {
    patchOk(8);
    await entrerEtape2();
    await saisir('wf-nom', 'Henri');
    await cliquer('wf-copier');
    expect(axios.patch).toHaveBeenCalledTimes(1);
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('https://afroboost.com/api/share/duo/T1?v=8');
    expect(postsVers('/chain/share')[0][1]).toEqual({ channel: 'copy' });
  });

  test('Partager (natif) avec modif en attente → PATCH puis navigator.share avec la nouvelle URL', async () => {
    patchOk(6);
    navigator.share = jest.fn(() => Promise.resolve());
    await entrerEtape2();
    await saisir('wf-nom', 'Henri');
    await cliquer('wf-partager');
    expect(axios.patch).toHaveBeenCalledTimes(1);
    expect(navigator.share.mock.calls[0][0].url).toBe('https://afroboost.com/api/share/duo/T1?v=6');
  });

  test('QR → après enregistrement, code du share_url courant', async () => {
    patchOk(6);
    await entrerEtape2();
    await saisir('wf-nom', 'Henri');
    await cliquer('wf-qr');
    expect(axios.patch).toHaveBeenCalledTimes(1);
    expect(par('qr-svg').getAttribute('data-value')).toBe('https://afroboost.com/api/share/duo/T1?v=6');
  });

  test('QR : « C’est fait » enregistre le partage avec le canal qr', async () => {
    patchOk(6);
    await entrerEtape2();
    await cliquer('wf-qr');
    await cliquer('wf-qr-fait');
    const partage = postsVers('/chain/share')[0];
    expect(partage).toBeDefined();
    expect(partage[1]).toEqual(expect.objectContaining({ channel: 'qr' }));
  });

  test('photo : envoi (multipart + X-Chain-Key) → PATCH photo_url → aperçu', async () => {
    patchOk(5);
    await entrerEtape2();
    expect(par('wf-photo-logo')).not.toBeNull(); // pas de photo : logo Afroboost
    expect(par('wf-photo-ajouter').textContent).toContain('Ajouter une photo');
    const f = new File(['x'], 'moi.jpg', { type: 'image/jpeg' });
    const input = par('wf-photo-fichier');
    expect(input.getAttribute('accept')).toBe('image/*');
    Object.defineProperty(input, 'files', { value: [f], configurable: true });
    await act(async () => { input.dispatchEvent(new Event('change', { bubbles: true })); });
    await vider();
    const envoi = postsVers('/chain/photo')[0];
    expect(envoi[1]).toBeInstanceOf(FormData);
    expect(envoi[1].get('file')).toBe(f);
    expect(envoi[2].headers).toEqual({ 'X-Chain-Key': 'K1' });
    expect(par('wf-photo-img').getAttribute('src')).toBe('/api/files/p1.jpg');
    expect(par('bandeau-photo').getAttribute('src')).toBe('/api/files/p1.jpg');
    await attendre(500);
    expect(axios.patch).toHaveBeenCalledTimes(1);
    expect(axios.patch.mock.calls[0][1].photo_url).toBe('/api/files/p1.jpg');
  });

  test('photo refusée côté navigateur (type) → message, aucun envoi', async () => {
    await entrerEtape2();
    const input = par('wf-photo-fichier');
    Object.defineProperty(input, 'files', { value: [new File(['x'], 'a.gif', { type: 'image/gif' })], configurable: true });
    await act(async () => { input.dispatchEvent(new Event('change', { bubbles: true })); });
    await vider();
    expect(par('wf-photo-erreur').textContent).toContain('JPEG, PNG ou WebP');
    expect(postsVers('/chain/photo').length).toBe(0);
  });

  test('photo_suggeree → préremplie, posée sur la carte par l’enregistrement automatique', async () => {
    patchOk(5);
    await entrerEtape2({ enfant: CHILD(3, { photo_suggeree: 'https://res.cloudinary.com/dtm0r7hwq/moi.jpg' }) });
    expect(par('wf-photo-img').getAttribute('src')).toBe('https://res.cloudinary.com/dtm0r7hwq/moi.jpg');
    expect(par('bandeau-photo').getAttribute('src')).toBe('https://res.cloudinary.com/dtm0r7hwq/moi.jpg');
    expect(par('wf-photo-ajouter').textContent).toContain('Changer de photo');
    await attendre(500);
    expect(axios.patch.mock.calls[0][1].photo_url).toBe('https://res.cloudinary.com/dtm0r7hwq/moi.jpg');
  });

  test('sans photo : logo Afroboost, jamais la photo du parrain, aucun PATCH', async () => {
    axios.get.mockResolvedValue({ data: Object.assign({}, PUB, { sponsor_photo_url: 'https://res.cloudinary.com/x/coach.jpg' }) });
    routerPost();
    await monter(<InvitationDuo token="T0" />);
    await cliquer('wf-continuer');
    expect(par('wf-photo-logo')).not.toBeNull();
    expect(par('bandeau-avatar-afroboost')).not.toBeNull();
    expect(conteneur.querySelector('.cp-wf-perso').innerHTML).not.toContain('coach.jpg');
    await attendre(1500);
    expect(axios.patch).not.toHaveBeenCalled();
  });

  test('WhatsApp (+41 par défaut) + consentement → envoyés ; le numéro préremplit l’inscription', async () => {
    patchOk(5);
    await entrerEtape2();
    expect(par('wf-indicatif').value).toBe('+41');
    expect(par('wf-consent').checked).toBe(false);
    expect(conteneur.textContent).toContain(TEXTE_CONSENT_CONTACT);
    await saisir('wf-whatsapp-numero', '079 123 45 67');
    await cliquer('wf-consent');
    await attendre(500);
    expect(axios.patch).toHaveBeenCalledTimes(1);
    expect(axios.patch.mock.calls[0][1]).toEqual(expect.objectContaining({ whatsapp: '+41 79 123 45 67', consent_contact: true }));
    window.open = jest.fn(() => null);
    await cliquer('wf-whatsapp');
    expect(par('invitation-whatsapp').value).toBe('+41 79 123 45 67');
  });

  test('numéro en cours de frappe (< 8 chiffres) : pas d’envoi automatique', async () => {
    patchOk(5);
    await entrerEtape2();
    await saisir('wf-whatsapp-numero', '079 12');
    await attendre(1500);
    expect(axios.patch).not.toHaveBeenCalled();
  });

  test('422 (numéro invalide) → message clair, pas de relance en boucle, AUCUN partage d’une version non enregistrée', async () => {
    axios.patch.mockRejectedValue({ response: { status: 422, headers: {}, data: { detail: 'whatsapp invalide' } } });
    const fen = { location: { href: '' }, close: jest.fn() };
    await entrerEtape2();
    await saisir('wf-whatsapp-numero', '12345678901');
    await attendre(500);
    expect(axios.patch).toHaveBeenCalledTimes(1);
    expect(par('wf-erreur-maj').textContent).toContain('numéro WhatsApp n’est pas valide');
    await attendre(3000);
    expect(axios.patch).toHaveBeenCalledTimes(1); // pas de boucle
    window.open = jest.fn(() => fen);
    await cliquer('wf-whatsapp');
    expect(axios.patch).toHaveBeenCalledTimes(2); // retentée au clic
    expect(fen.location.href).toBe('');
    expect(fen.close).toHaveBeenCalled();
    await cliquer('wf-copier');
    expect(navigator.clipboard.writeText).not.toHaveBeenCalled();
    expect(postsVers('/chain/share').length).toBe(0);
  });

  test('numeroWhatsAppChaine : indicatif, 0 national, numéro déjà international, vide', () => {
    expect(numeroWhatsAppChaine('+41', '079 123 45 67')).toBe('+41 79 123 45 67');
    expect(numeroWhatsAppChaine('+33', '6 12 34 56 78')).toBe('+33 6 12 34 56 78');
    expect(numeroWhatsAppChaine('+41', '+225 07 00 00 00')).toBe('+225 07 00 00 00');
    expect(numeroWhatsAppChaine('+41', '0041 79 000 00 00')).toBe('0041 79 000 00 00');
    expect(numeroWhatsAppChaine('+41', '  ')).toBe('');
  });

  test('champs à 16 px sur mobile (pas de zoom iOS)', () => {
    const fs = require('fs');
    const path = require('path');
    const css = fs.readFileSync(path.join(__dirname, '../wizardFilleul.css'), 'utf8');
    expect(css).toMatch(/\.cp-wf-tel \.cp-input \{[^}]*font-size: 16px/);
    expect(css).toMatch(/\.cp-select\.cp-wf-indicatif \{[^}]*font-size: 16px/);
  });
});

/**
 * V610m — « DEVIENS AFROBOOSTEUR » partout où une place est CONFIRMÉE.
 *
 * Essai : aucun audio sur la première page (il vit sur « Ton essai est prêt »).
 * Payant : confirmation par le WEBHOOK, puis « Ta place est réservée ! », l'événement,
 * Deviens Afroboosteur + audio + gros « Inviter mes amis ». Lien rouvert sur le même
 * appareil : « Tu participes » (re-vérifié par le serveur), jamais un 2e paiement d'emblée.
 * Membre 8 mois : « Réserve gratuitement » -> l'espace s'ouvre sur CET événement.
 * Espace : chaque réservation d'événement porte son « Inviter mes amis ».
 * axios et fetch sont mockés : aucun réseau, aucune donnée réelle.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn(), create: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } }));
// eslint-disable-next-line import/first
import axios from 'axios';
// eslint-disable-next-line import/first
import InvitationPublique from '../InvitationPublique';
// eslint-disable-next-line import/first
import EvenementsOfferts from '../EvenementsOfferts';
// eslint-disable-next-line import/first
import MesEvenementsInvitation from '../MesEvenementsInvitation';
// eslint-disable-next-line import/first
import { lireIntentionMembre, lireParticipation, memoriserParticipation, retenirIntentionMembre, offreDeLInvitation } from '../../utils/participationEvenement';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let conteneur = null; let racine = null;
function rendre(el) { conteneur = document.createElement('div'); document.body.appendChild(conteneur); racine = createRoot(conteneur); racine.render(el); }
let play;
beforeEach(() => {
  play = jest.spyOn(window.HTMLMediaElement.prototype, 'play').mockImplementation(() => Promise.resolve());
  jest.spyOn(window.HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
});
afterEach(() => {
  if (racine) act(() => racine.unmount());
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
  delete global.fetch; window.localStorage.clear(); window.history.replaceState({}, '', '/');
  jest.restoreAllMocks(); jest.clearAllMocks();
});
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
jest.setTimeout(15000);
async function attendre(fn) { let e; for (let i = 0; i < 300; i += 1) { try { fn(); return; } catch (x) { e = x; } await act(async () => { await new Promise((r) => setTimeout(r, 20)); }); } throw e; }
const json = (corps, ok = true, status = 200) => Promise.resolve({ ok, status, json: () => Promise.resolve(corps) });

const JETON = 'JetonDeBassi1234567';
const SILENT = {
  type: 'event_paid', title: 'AFROBOOST SILENT — ÉDITION SPÉCIALE', date_label: 'mercredi 28 octobre', time_label: '18:45',
  lieu: 'Chemin des Valangines 97, 2000 Neuchâtel', inviter_display: { prenom: 'Bassi' }, gratuit_membres: true,
  audio_partage_url: '/api/files/a1/afro.mp3', audio_url: null, reservation_directe: { offer_id: 'OFF-1' },
  prix_actif: { prix: 30, palier: 'regular', libelle: 'Tarif' }, cible: '/?offre=OFF-1&inv=x',
};
const ESSAI = { type: 'trial', title: 'Ton premier cours Afroboost est offert', inviter_display: { prenom: 'Bassi' },
  audio_url: '/api/files/a1/afro.mp3', date_label: 'mercredi 14 octobre', time_label: '18:45', cible: '/duo/c/x' };
const RELAIS_SOPHIE = { jeton: 'JetonSophie1234567890', share_url: 'https://afroboost.com/i/JetonSophie1234567890', prenom: 'Sophie', generation: 2 };

describe('V610m — Essai gratuit : pas d’audio sur la première page', () => {
  test('A — page initiale de l’essai : aucun lecteur audio (audio_url conservé côté serveur)', async () => {
    global.fetch = jest.fn(() => json(ESSAI));
    await act(async () => { rendre(<InvitationPublique token={JETON} />); });
    await attendre(() => expect(q('inv-pub-titre')).toBeTruthy());
    expect(q('inv-pub-offert')).toBeTruthy();
    expect(q('inv-pub-audio')).toBeNull();
    expect(document.querySelector('audio')).toBeNull();
    expect(play).not.toHaveBeenCalled();
  });
  test('un événement avec un mot audio AVANT réservation le garde (comportement inchangé)', async () => {
    global.fetch = jest.fn(() => json({ ...SILENT, type: 'event_free', audio_url: '/api/files/a2/mot.mp3', reservation_directe: null }));
    await act(async () => { rendre(<InvitationPublique token={JETON} />); });
    await attendre(() => expect(q('inv-pub-audio')).toBeTruthy());
  });
});

describe('V610m — événement payant : confirmation puis boule de neige', () => {
  test('D/E/F — retour Stripe : rien avant le webhook ; puis « Ta place est réservée ! » + événement + Deviens Afroboosteur + audio + Inviter mes amis', async () => {
    window.history.replaceState({}, '', `/i/${JETON}?paiement=ok&cs=cs_test_ABC123456`);
    let n = 0;
    global.fetch = jest.fn((url) => {
      const u = String(url);
      if (u.includes('/relais/session/')) { n += 1; return n < 2 ? json({ detail: 'x' }, false, 404) : json({ ...RELAIS_SOPHIE, place_confirmee: true }); }
      if (u.includes('/api/invitation/publique/')) return json(SILENT);
      return json({});
    });
    await act(async () => { rendre(<InvitationPublique token={JETON} />); });
    await attendre(() => expect(q('inv-pub-confirmation-attente')).toBeTruthy());
    expect(q('inv-pub-confirmation-attente').textContent).toBe('Confirmation de ton paiement…');
    expect(document.querySelector('audio')).toBeNull();                     // E : pas d'audio avant la preuve
    await attendre(() => expect(q('inv-pub-place-reservee').textContent).toBe('Ta place est réservée !'));
    await attendre(() => expect(q('afroboosteur-titre')).toBeTruthy());
    const ordre = [...document.querySelectorAll('[data-testid]')].map((e) => e.dataset.testid);
    expect(ordre.indexOf('inv-pub-place-reservee')).toBeLessThan(ordre.indexOf('inv-pub-confirmation-evenement'));
    expect(ordre.indexOf('inv-pub-confirmation-evenement')).toBeLessThan(ordre.indexOf('afroboosteur-titre'));
    expect(ordre.indexOf('afroboosteur-titre')).toBeLessThan(ordre.indexOf('afroboosteur-audio'));
    expect(ordre.indexOf('afroboosteur-audio')).toBeLessThan(ordre.indexOf('inviter-partager'));
    expect(ordre.indexOf('inviter-partager')).toBeLessThan(ordre.indexOf('inviter-copier-direct'));
    expect(q('inviter-lien').textContent).toContain('afroboost.com/i/JetonSophie1234567890');   // SON lien, pas celui de Bassi
    expect(q('inv-pub-cta')).toBeNull();                                      // aucun bouton de paiement
    expect(lireParticipation(JETON)).toEqual({ cs: 'cs_test_ABC123456' });
  });

  test('M — « Inviter mes amis » deux fois : WhatsApp ouvert à chaque geste, aucun appel serveur de création, jamais « envoyé »', async () => {
    window.history.replaceState({}, '', `/i/${JETON}?paiement=ok&cs=cs_test_ABC123456`);
    global.fetch = jest.fn((url) => (String(url).includes('/relais/session/') ? json({ ...RELAIS_SOPHIE, place_confirmee: true })
      : String(url).includes('/api/invitation/publique/') ? json(SILENT) : json({})));
    const ouvrir = jest.spyOn(window, 'open').mockImplementation(() => null);
    await act(async () => { rendre(<InvitationPublique token={JETON} />); });
    await attendre(() => expect(q('afroboosteur-titre')).toBeTruthy());
    const avant = global.fetch.mock.calls.filter((c) => /relais\/session/.test(String(c[0]))).length;
    await act(async () => { q('inviter-partager').click(); });
    await act(async () => { q('inviter-whatsapp').click(); q('inviter-whatsapp').click(); });
    expect(ouvrir).toHaveBeenCalledTimes(2);
    expect(global.fetch.mock.calls.filter((c) => /relais\/session/.test(String(c[0]))).length).toBe(avant);
    const txt = decodeURIComponent(String(ouvrir.mock.calls[0][0]));
    expect(txt).toContain('JetonSophie1234567890');
    expect(txt).not.toMatch(/gratuit pour toi/i);
    expect(document.body.textContent).not.toMatch(/envoy[ée]/i);
  });

  test('L/13 — lien ROUVERT sur le même appareil : « Tu participes » (vérifié par le serveur), aucun paiement proposé d’emblée', async () => {
    memoriserParticipation(JETON, { cs: 'cs_test_ABC123456' });
    global.fetch = jest.fn((url) => (String(url).includes('/relais/session/') ? json({ ...RELAIS_SOPHIE, place_confirmee: true })
      : String(url).includes('/api/invitation/publique/') ? json(SILENT) : json({})));
    await act(async () => { rendre(<InvitationPublique token={JETON} />); });
    await attendre(() => expect(q('inv-pub-place-reservee').textContent).toBe('Ta place est déjà réservée'));   // V618L
    expect(q('inv-pub-cta')).toBeNull();
    await attendre(() => expect(q('inviter-partager')).toBeTruthy());
    expect(play).not.toHaveBeenCalled();                                     // pas de relecture automatique au retour
    expect(global.fetch.mock.calls.some((c) => /create-checkout-session/.test(String(c[0])))).toBe(false);
    // « Voir l'invitation » -> la page normale (ex. réserver pour quelqu'un d'autre)
    await act(async () => { q('inv-pub-voir-invitation').click(); });
    expect(q('inv-pub-cta')).toBeTruthy();
  });

  test('mémoire non confirmée par le serveur (autre état) : la page normale, jamais « réservée » sans preuve', async () => {
    memoriserParticipation(JETON, { cs: 'cs_test_ABC123456' });
    global.fetch = jest.fn((url) => (String(url).includes('/relais/session/') ? json({ detail: 'x' }, false, 404)
      : String(url).includes('/api/invitation/publique/') ? json(SILENT) : json({})));
    await act(async () => { rendre(<InvitationPublique token={JETON} />); });
    await attendre(() => expect(q('inv-pub-cta')).toBeTruthy());
    expect(q('inv-pub-place-reservee')).toBeNull();
  });

  test('place OFFERTE déjà prise sur cet appareil (membre) : « Tu participes » + son lien, sans paiement', async () => {
    memoriserParticipation(JETON, { relais: RELAIS_SOPHIE });
    global.fetch = jest.fn((url) => (String(url).includes('/api/invitation/publique/') ? json(SILENT) : json({})));
    await act(async () => { rendre(<InvitationPublique token={JETON} />); });
    await attendre(() => expect(q('inv-pub-place-reservee').textContent).toBe('Ta place est déjà réservée'));   // V618L
    await attendre(() => expect(q('inviter-lien').textContent).toContain('JetonSophie1234567890'));
    expect(q('inv-pub-cta')).toBeNull();
  });
});

describe('V610m — membre 8 mois : directement sur CET événement', () => {
  test('I — « Réserve gratuitement » retient l’événement visé, puis ouvre l’espace', async () => {
    window.localStorage.setItem('afroboost_espace_token', JSON.stringify({ token: 't', code: 'AFR-M1', expires_at: '2999-01-01' }));
    const assign = jest.fn(); delete window.location; window.location = { href: '', search: '', origin: 'http://localhost', assign };
    global.fetch = jest.fn(() => json(SILENT));
    await act(async () => { rendre(<InvitationPublique token={JETON} />); });
    await attendre(() => expect(q('inv-pub-membre-compact')).toBeTruthy());
    await act(async () => { q('inv-pub-membre-compact').click(); });
    expect(lireIntentionMembre()).toEqual({ offre: 'OFF-1', jeton: JETON });
  });

  test('I — espace : la carte visée passe EN TÊTE, réserve à 0 CHF -> « Ta place est réservée ! » + Afroboosteur + Inviter mes amis', async () => {
    retenirIntentionMembre('OFF-1', JETON);
    axios.post.mockResolvedValue({ data: { success: true, prix: 0, relais: RELAIS_SOPHIE } });
    global.fetch = jest.fn((url) => (String(url).includes('/api/invitation/publique/') ? json(SILENT) : json({})));
    const AUTRE = { offer_id: 'OFF-0', titre: 'Autre soirée', datetime: '2026-11-04T18:45:00', lieu: 'X', deja_reserve: false };
    const VISE = { offer_id: 'OFF-1', titre: 'AFROBOOST SILENT — ÉDITION SPÉCIALE', datetime: '2026-10-28T18:45:00', lieu: 'Valangines', deja_reserve: false };
    await act(async () => { rendre(<EvenementsOfferts evenements={[AUTRE, VISE]} accessCode="AFR-M1" memberSlug="" />); });
    const cartes = [...document.querySelectorAll('[data-testid^="evt-offert-OFF"]')];
    expect(cartes[0].dataset.testid).toBe('evt-offert-OFF-1');
    expect(cartes[0].dataset.vise).toBe('1');
    // V618L : la carte n'est replacée que si elle est HORS de l'écran (jsdom : déjà en haut).
    await act(async () => { cartes[0].querySelector('[data-testid="evt-offert-reserver"]').click(); });
    await attendre(() => expect(q('evt-offert-confirme').textContent).toContain('Ta place est réservée !'));
    expect(String(axios.post.mock.calls[0][0])).toMatch(/\/evenement\/OFF-1\/offert$/);   // 0 CHF, pas de Stripe
    await attendre(() => expect(q('afroboosteur-titre')).toBeTruthy());
    expect(q('inviter-partager').textContent).toMatch(/Inviter mes amis/);   // V618L
    await attendre(() => expect(play).toHaveBeenCalledTimes(1));
    expect(lireIntentionMembre()).toBeNull();                                  // intention servie
    expect(lireParticipation(JETON)).toEqual({ relais: { jeton: RELAIS_SOPHIE.jeton, share_url: RELAIS_SOPHIE.share_url } });
    expect(document.body.textContent).not.toMatch(/CHF|Stripe|TWINT/);
  });

  test('événement visé NON offert à ce compte : on le dit, rien n’est réservé', async () => {
    retenirIntentionMembre('OFF-9', JETON);
    await act(async () => { rendre(<EvenementsOfferts evenements={[]} accessCode="AFR-M1" memberSlug="" />); });
    expect(q('evt-offert-non-eligible').textContent).toContain('Cet événement n’est pas inclus dans ton abonnement actuel.');
    expect(q('evt-offert-tarif-actuel').textContent).toBe('Réserver au tarif actuel');
    expect(q('evt-offert-tarif-actuel').getAttribute('href')).toBe(`/i/${JETON}`);
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('intention périmée (> 24 h) : ignorée', () => {
    window.localStorage.setItem('af_evt_vise', JSON.stringify({ offre: 'OFF-1', jeton: JETON, t: Date.now() - 25 * 3600 * 1000 }));
    expect(lireIntentionMembre()).toBeNull();
  });
});

describe('V610m — espace : ma réservation et son « Inviter mes amis »', () => {
  const LISTE = { evenements: [
    { offer_id: 'OFF-1', titre: 'AFROBOOST SILENT — ÉDITION SPÉCIALE', occurrence: '2026-10-28T18:45:00', lieu: 'Valangines', relais: RELAIS_SOPHIE },
    { offer_id: 'OFF-2', titre: 'Autre', occurrence: '2026-11-04T18:45:00', lieu: '', relais: { ...RELAIS_SOPHIE, jeton: 'JetonAutre12345678901', share_url: 'https://afroboost.com/i/JetonAutre12345678901' } },
  ] };
  test('12 — liste du serveur (session d’espace), « Ta place est réservée » + Inviter mes amis ; une place offerte n’est pas répétée', async () => {
    global.fetch = jest.fn((url) => (String(url).includes('/mes-evenements') ? json(LISTE) : json(SILENT)));
    await act(async () => { rendre(<MesEvenementsInvitation accessCode="AFR-P1" jetonEspace="tok" slug="" offresDejaAffichees={[{ offer_id: 'OFF-2' }]} />); });
    await attendre(() => expect(q('mes-evenements')).toBeTruthy());
    const [url, opts] = global.fetch.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/invitation\/relais\/mes-evenements$/);
    expect(opts.headers['x-espace-token']).toBe('tok');
    expect(JSON.parse(opts.body)).toEqual({ code: 'AFR-P1', slug: '' });
    expect(document.querySelectorAll('[data-testid^="mes-evenements-Jeton"]')).toHaveLength(1);
    expect(q('mes-evenements-confirme').textContent).toContain('Ta place est réservée');
    await act(async () => { q('mes-evenements-inviter').click(); });
    await attendre(() => expect(q('inviter-lien').textContent).toContain('JetonSophie1234567890'));
  });
  test('sans session d’espace : aucun appel, rien d’affiché ; refus serveur : rien d’affiché', async () => {
    global.fetch = jest.fn(() => json({ detail: 'x' }, false, 403));
    await act(async () => { rendre(<MesEvenementsInvitation accessCode="AFR-P1" jetonEspace="" slug="" />); });
    expect(global.fetch).not.toHaveBeenCalled();
    act(() => racine.unmount()); conteneur.remove(); racine = null;
    await act(async () => { rendre(<MesEvenementsInvitation accessCode="AFR-P1" jetonEspace="tok" slug="" />); });
    await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
    expect(q('mes-evenements')).toBeNull();
  });
});

describe('V610m — moteur pur', () => {
  test('offre de l’invitation : réservation directe, sinon /?offre=', () => {
    expect(offreDeLInvitation({ reservation_directe: { offer_id: 'OFF-1' } })).toBe('OFF-1');
    expect(offreDeLInvitation({ target_url: '/?offre=abc-12&inv=x' })).toBe('abc-12');
    expect(offreDeLInvitation({})).toBe('');
  });
  test('mémoire : jamais autre chose que {cs} ou {relais https}', () => {
    memoriserParticipation(JETON, { cs: 'pas-un-cs' });
    expect(lireParticipation(JETON)).toBeNull();
    memoriserParticipation(JETON, { relais: { jeton: 'JetonSophie1234567890', share_url: 'javascript:alert(1)' } });
    expect(lireParticipation(JETON)).toBeNull();
    window.localStorage.setItem(`af_evt_participe_${JETON}`, '{bad json');
    expect(lireParticipation(JETON)).toBeNull();
  });
});

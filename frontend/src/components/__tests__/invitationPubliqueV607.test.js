/**
 * V607 — page publique /i/<jeton> et bloc « Invite tes amis » (facultatif).
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn(), create: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } }));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let conteneur = null;
let racine = null;
function render(el) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  racine.render(el);
  return { container: conteneur };
}
afterEach(() => {
  if (racine) act(() => racine.unmount());
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
});
const screen = { getByTestId: (id) => { const e = document.querySelector(`[data-testid="${id}"]`); if (!e) throw new Error('absent: ' + id); return e; } };
async function waitFor(fn) {
  let derniere;
  for (let i = 0; i < 40; i += 1) {
    try { fn(); return; } catch (e) { derniere = e; }
    // eslint-disable-next-line no-await-in-loop
    await act(async () => { await new Promise((r) => setTimeout(r, 25)); });
  }
  throw derniere;
}
import InvitationPublique, { cibleSure, urlSure } from '../InvitationPublique';
import InviterMesAmis from '../InviterMesAmis';

function reponse(corps, ok = true) {
  return Promise.resolve({ ok, status: ok ? 200 : 404, json: () => Promise.resolve(corps) });
}

describe('InvitationPublique — utilitaires', () => {
  test('cibleSure garde le CHEMIN, jamais un autre site', () => {
    expect(cibleSure('https://afroboost.com/?offre=x&inv=T')).toBe('/?offre=x&inv=T');
    expect(cibleSure('http://127.0.0.1:8001/duo/c/abc')).toBe('/duo/c/abc');
    expect(cibleSure('https://pirate.example/vol')).toBe('/vol');
    expect(cibleSure('')).toBe('/');
  });
  test('urlSure : https ou chemin du site, jamais javascript: ni //hôte', () => {
    expect(urlSure('https://res.cloudinary.com/a.mp4')).toBe('https://res.cloudinary.com/a.mp4');
    expect(urlSure('/api/files/x/a.mp4')).toBe('/api/files/x/a.mp4');
    expect(urlSure('javascript:alert(1)')).toBe('');
    expect(urlSure('//pirate.example/a.mp4')).toBe('');
    expect(urlSure('http://a.ch/x.mp4')).toBe('');
  });
});

describe('InvitationPublique — rendu par type', () => {
  afterEach(() => { delete global.fetch; });

  test('événement payant : prix actif, paliers, urgence ; vidéo SANS lecture automatique', async () => {
    global.fetch = jest.fn((url) => (String(url).includes('/api/invitation/publique/')
      ? reponse({ type: 'event_paid', title: 'Gala', date_label: 'dimanche 25 octobre', time_label: '20:00', lieu: 'Salle',
        inviter_display: { prenom: 'Bassi' }, cible: 'https://afroboost.com/?offre=o&inv=T', cta_label: 'Je réserve ma place',
        video_url: '/api/files/v/a.mp4', audio_url: '/api/files/m/a.mp3',
        prix_actif: { prix: 25, palier: 'early_bird', libelle: 'Tarif lancement',
          paliers: [{ palier: 'early_bird', libelle: 'Tarif lancement', prix: 25, actif: true }, { palier: 'standard', libelle: 'Tarif standard', prix: 35, actif: false }],
          prochain: { palier: 'standard', prix: 35, a_partir_de: '2026-10-18T19:00:00+00:00' } } })
      : reponse({}, true)));
    await act(async () => { render(<InvitationPublique token="T123456789012345678" />); });
    await waitFor(() => expect(screen.getByTestId('inv-pub-prix-actif').textContent).toBe('25 CHF'));
    expect(screen.getByTestId('inv-pub-palier-early_bird').getAttribute('data-actif')).toBe('1');
    expect(screen.getByTestId('inv-pub-urgence').textContent).toMatch(/Plus tu réserves tôt/);
    const v = screen.getByTestId('inv-pub-video');
    expect(v.autoplay).toBe(false);
    expect(v.getAttribute('preload')).toBe('none');
    expect(screen.getByTestId('inv-pub-audio')).toBeTruthy();
    expect(document.querySelector('audio').autoplay).toBe(false);
    // suivi : lien ouvert (honnête, jamais « envoyé »)
    const suivis = global.fetch.mock.calls.filter((c) => String(c[0]).includes('/api/invitation/suivi'));
    expect(suivis.length).toBe(1);
    expect(JSON.parse(suivis[0][1].body).evenement).toBe('lien_ouvert');
  });

  test('essai : « premier cours offert », aucun prix ; gratuit : « Gratuit », jamais 0 CHF', async () => {
    global.fetch = jest.fn(() => reponse({ type: 'trial', inviter_display: { prenom: 'Bassi' }, cible: '/duo/c/T', date_label: 'mercredi 14 octobre' }));
    await act(async () => { render(<InvitationPublique token="T123456789012345678" />); });
    await waitFor(() => expect(screen.getByTestId('inv-pub-offert')).toBeTruthy());
    expect(document.body.textContent).not.toMatch(/CHF/);
    expect(screen.getByTestId('inv-pub-titre').textContent).toBe("Bassi t'invite à découvrir Afroboost");
  });

  test('invitation indisponible -> message, aucun crash', async () => {
    global.fetch = jest.fn(() => reponse({}, false));
    await act(async () => { render(<InvitationPublique token="T123456789012345678" />); });
    await waitFor(() => expect(screen.getByTestId('inv-pub-indisponible')).toBeTruthy());
  });
});

describe('InviterMesAmis — facultatif, jamais sans invitation', () => {
  afterEach(() => { delete global.fetch; window.localStorage.clear(); });

  test("sans invitation mémorisée : rien n'est affiché ni demandé", async () => {
    global.fetch = jest.fn();
    let r;
    await act(async () => { r = render(<InviterMesAmis sessionId="cs_test_123456" />); });
    expect(r.container.innerHTML).toBe('');
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test('avec invitation + accès : le lien personnel est proposé', async () => {
    window.localStorage.setItem('af_invitation', JSON.stringify({ t: 'JetonInvitation1234', offre: 'o', at: Date.now() }));
    global.fetch = jest.fn((url) => (String(url).includes('/relais/inscription')
      ? reponse({ jeton: 'JetonPerso12345678', share_url: 'https://afroboost.com/i/JetonPerso12345678', prenom: 'Paul', generation: 1 })
      : reponse({ type: 'event_free', title: 'Fête' })));
    await act(async () => { render(<InviterMesAmis codeAcces="AFR-ABC123" />); });
    await waitFor(() => expect(screen.getByTestId('inviter-mes-amis')).toBeTruthy());
    expect(screen.getByTestId('inviter-lien').textContent).toMatch(/afroboost\.com\/i\/JetonPerso12345678/);
  });
});

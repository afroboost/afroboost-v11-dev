/**
 * V610 — place OFFERTE (membres 8 mois) dans l'espace, lien personnel après un
 * billet d'événement à réservation automatique, mention « offert » sur la page
 * d'invitation. Le DROIT est décidé par le serveur : ici, on vérifie l'écran.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn(), create: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } }));
// eslint-disable-next-line import/first
import axios from 'axios';
// eslint-disable-next-line import/first
import EvenementsOfferts, { quandEvenement } from '../EvenementsOfferts';
// eslint-disable-next-line import/first
import InviterMesAmis from '../InviterMesAmis';
// eslint-disable-next-line import/first
import InvitationPublique from '../InvitationPublique';
// eslint-disable-next-line import/first
import AccesMembreEvenement, { TEXTE_NEUTRE } from '../AccesMembreEvenement';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
// V618M : la carte événement lit les conditions publiées AU MOMENT de réserver (aucune ici).
beforeEach(() => { axios.get.mockResolvedValue({ data: { required: false } }); });
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
  delete global.fetch;
  window.localStorage.clear();
  jest.clearAllMocks();
});
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
async function attendre(fn) {
  let derniere;
  for (let i = 0; i < 40; i += 1) {
    try { fn(); return; } catch (e) { derniere = e; }
    // eslint-disable-next-line no-await-in-loop
    await act(async () => { await new Promise((r) => setTimeout(r, 25)); });
  }
  throw derniere;
}
const reponse = (corps, ok = true) => Promise.resolve({ ok, status: ok ? 200 : 404, json: () => Promise.resolve(corps) });
const EVT = { offer_id: 'OFF1', titre: 'AFROBOOST SILENT — ÉDITION SPÉCIALE', datetime: '2026-10-28T18:45:00',
  lieu: 'Chem. des Valangines 97, 2000 Neuchâtel', deja_reserve: false };

describe('V610 — EvenementsOfferts (espace)', () => {
  test('date lisible « mercredi 28 octobre · 18h45 »', () => {
    expect(quandEvenement('2026-10-28T18:45:00')).toBe('mercredi 28 octobre · 18h45');
    expect(quandEvenement('n/a')).toBe('');
  });

  test('rien sans événement offert (liste vide ou absente)', async () => {
    let r;
    await act(async () => { r = render(<EvenementsOfferts evenements={[]} accessCode="AFR-1" />); });
    expect(r.container.innerHTML).toBe('');
  });

  test('« Ta place est offerte avec ton abonnement » -> réserve à 0 CHF (route offerte, aucun paiement) -> lien perso', async () => {
    window.localStorage.setItem('af_invitation', JSON.stringify({ t: 'JetonInvitation1234', offre: 'OFF1', at: Date.now() }));
    axios.post.mockResolvedValue({ data: { success: true, prix: 0, deja_reserve: false,
      reservation: { id: 'R1' }, relais: { jeton: 'JetonSophie123456', share_url: 'https://afroboost.com/i/JetonSophie123456', prenom: 'Sophie', generation: 2 } } });
    global.fetch = jest.fn(() => reponse({ type: 'event_paid', title: 'AFROBOOST SILENT', inviter_display: { prenom: 'Sophie' } }));
    await act(async () => { render(<EvenementsOfferts evenements={[EVT]} accessCode="AFR-M1" memberSlug="" />); });
    expect(q('evt-offert-avantage').textContent).toBe('PLACE OFFERTE');   // V618M : l'avantage réel, dit simplement
    // V618L : la date sur une ligne, la VILLE sur la suivante (l'adresse complète est sur la page de l'événement)
    expect(q('evt-offert-quand').textContent).toBe('Mercredi 28 octobre · 18h45');
    expect(q('evt-offert-ville').textContent).toBe('Neuchâtel');
    await act(async () => { q('evt-offert-reserver').click(); });
    // V618L : la confirmation est le TITRE du haut (« Ta place est réservée ! »), jamais répétée dessous
    await attendre(() => expect(q('evt-offert-confirme-titre').textContent).toBe('Ta place est réservée !'));
    expect(q('evt-offert-reservee')).toBeNull();
    const [url, corps] = axios.post.mock.calls[0];
    expect(url).toMatch(/\/api\/subscriber\/space\/AFR-M1\/evenement\/OFF1\/offert$/);
    expect(corps.jeton_invitation).toBe('JetonInvitation1234');
    expect(corps).not.toHaveProperty('email');            // l'e-mail vient de la SESSION, jamais du corps
    await attendre(() => expect(q('inviter-lien').textContent).toMatch(/afroboost\.com\/i\/JetonSophie123456/));
    expect(document.body.textContent).not.toMatch(/CHF|Stripe|TWINT/);
  });

  test('refus serveur (abonnement non éligible) : message affiché, bouton toujours là', async () => {
    axios.post.mockRejectedValue({ response: { status: 403, data: { detail: "La place offerte est réservée aux membres dont l'abonnement 8 mois est actif à la date de l'événement." } } });
    await act(async () => { render(<EvenementsOfferts evenements={[EVT]} accessCode="AFR-M2" />); });
    await act(async () => { q('evt-offert-reserver').click(); });
    await attendre(() => expect(q('evt-offert-erreur').textContent).toMatch(/abonnement 8 mois est actif/));
    expect(q('evt-offert-reserver')).toBeTruthy();
  });

  test('déjà réservée : « Ta place est réservée » + « Inviter mes amis »', async () => {
    await act(async () => { render(<EvenementsOfferts evenements={[{ ...EVT, deja_reserve: true }]} accessCode="AFR-M1" />); });
    expect(q('evt-offert-reservee')).toBeTruthy();
    expect(q('evt-offert-lien')).toBeTruthy();
  });
});

describe('V610 — InviterMesAmis', () => {
  test('billet d\'événement acheté SANS invitation : le lien est demandé par la session Stripe', async () => {
    global.fetch = jest.fn((url) => (String(url).includes('/relais/session/')
      ? reponse({ jeton: 'JetonSam1234567890', share_url: 'https://afroboost.com/i/JetonSam1234567890', prenom: 'Sam', generation: 1 })
      : reponse({ type: 'event_paid', title: 'Silent' })));
    await act(async () => { render(<InviterMesAmis sessionId="cs_test_abc123" evenement />); });
    await attendre(() => expect(q('inviter-lien').textContent).toMatch(/JetonSam1234567890/));
  });

  test('achat ordinaire (pas un événement), sans invitation : rien n\'est demandé', async () => {
    global.fetch = jest.fn();
    let r;
    await act(async () => { r = render(<InviterMesAmis sessionId="cs_test_abc123" />); });
    expect(r.container.innerHTML).toBe('');
    expect(global.fetch).not.toHaveBeenCalled();
  });
});

describe('V610 — page d\'invitation', () => {
  test('mention « Offert si tu as un abonnement Afroboost 8 mois actif », sans plafond de places', async () => {
    global.fetch = jest.fn((url) => (String(url).includes('/api/invitation/publique/')
      ? reponse({ type: 'event_paid', title: 'AFROBOOST SILENT', date_label: 'mercredi 28 octobre', time_label: '18:45',
        lieu: 'Valangines', inviter_display: { prenom: 'Sophie' }, cible: '/?offre=o&inv=T', gratuit_membres: true,
        prix_actif: { prix: 25, palier: 'early_bird', libelle: 'Prévente', paliers: [],
          prochain: { palier: 'standard', prix: 30, a_partir_de: '2026-10-21T16:45:00+00:00' } } })
      : reponse({})));
    await act(async () => { render(<InvitationPublique token="T123456789012345678" />); });
    // V618L : une ligne sous le bouton de réservation ; au clic, l'étape e-mail SUR PLACE (pas dans « Lire plus »).
    await attendre(() => expect(q('inv-pub-membre-compact').textContent).toMatch(/^Déjà membre Afroboost \?\s*Voir mon tarif membre$/));
    expect(q('membre-lien')).toBeNull();
    await act(async () => { q('inv-pub-membre-compact').click(); });
    expect(q('membre-lien').textContent).toMatch(/Entre l'adresse e-mail liée à ton abonnement Afroboost\./);
    expect(q('membre-lien-envoyer').textContent).toBe("Recevoir mon lien d'accès");
    expect(q('inv-pub-prix-actif').textContent).toBe('25 CHF');
    expect(document.body.textContent).not.toMatch(/50 places|places maximum/);
  });
});

describe('V610b — AccesMembreEvenement : même bloc pour tous, rien ne fuit', () => {
  test("affiché sans AUCUN appel réseau (pas de recherche d'e-mail)", async () => {
    global.fetch = jest.fn();
    await act(async () => { render(<AccesMembreEvenement />); });
    expect(document.body.textContent).toMatch(/Déjà membre Afroboost \?/);
    expect(document.body.textContent).toMatch(/Ton abonnement peut te donner droit à un tarif spécial\. Découvre-le dans ton espace membre\./);
    expect(q('acces-membre-bouton').textContent).toBe('Accéder à mon espace membre');
    expect(axios.post).not.toHaveBeenCalled();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  async function envoyerAvec(reponseServeur) {
    global.fetch = jest.fn(() => Promise.resolve({ ok: reponseServeur === 200, status: reponseServeur,
      json: () => Promise.resolve(reponseServeur === 200 ? { success: true, email_masked: 'm***@x.ch' } : { detail: 'Aucun code abonné actif trouvé' }) }));
    await act(async () => { render(<AccesMembreEvenement libelle="Je suis membre" />); });
    await act(async () => { q('acces-membre-bouton').click(); });
    const champ = q('acces-membre-email');
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(champ, 'quelquun@example.com');
      champ.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => { q('acces-membre-envoyer').click(); });
    await attendre(() => expect(q('acces-membre-neutre')).toBeTruthy());
    const texte = q('acces-membre-evenement').textContent;
    act(() => racine.unmount()); conteneur.remove(); racine = null; conteneur = null;
    return texte;
  }

  test("sans session : e-mail d'un membre (200) ou d'un inconnu (404) -> écran IDENTIQUE, neutre", async () => {
    const avecCompte = await envoyerAvec(200);
    const sansCompte = await envoyerAvec(404);
    expect(avecCompte).toBe(sansCompte);
    expect(avecCompte).toMatch(new RegExp(TEXTE_NEUTRE.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    expect(avecCompte).not.toMatch(/m\*\*\*@|Aucun code|actif trouvé|membre confirmé/);
    expect(global.fetch.mock.calls[0][0]).toMatch(/\/api\/subscriber\/recover$/);
  });

  test('session déjà ouverte sur cet appareil : direction son espace, aucun appel', async () => {
    global.fetch = jest.fn();
    window.localStorage.setItem('afroboost_espace_token', JSON.stringify({ token: 'tok', code: 'AFR-M1', slug: '', expires_at: '2099-01-01T00:00:00Z' }));
    const avant = window.location.href;
    delete window.location; window.location = { href: avant };
    await act(async () => { render(<AccesMembreEvenement />); });
    await act(async () => { q('acces-membre-bouton').click(); });
    expect(window.location.href).toMatch(/\/espace\/AFR-M1/);
    expect(global.fetch).not.toHaveBeenCalled();
  });
});

describe('V610d — « Deviens Afroboosteur » : audio APRÈS réservation, événement payant seulement', () => {
  const RELAIS = { jeton: 'JetonSophie123456', share_url: 'https://afroboost.com/i/JetonSophie123456', prenom: 'Sophie', generation: 1 };
  const DETAILS = { type: 'event_paid', title: 'AFROBOOST SILENT — ÉDITION SPÉCIALE', inviter_display: { prenom: 'Sophie' },
    date_label: 'mercredi 28 octobre', time_label: '18:45', lieu: 'Valangines',
    audio_partage_url: '/api/files/a1/afroboosteur.mp3', audio_url: null, prix_actif: { prix: 25, palier: 'early_bird', libelle: 'Prévente' } };
  let play; let pause;
  beforeEach(() => {
    play = jest.spyOn(window.HTMLMediaElement.prototype, 'play').mockImplementation(function () {
      Object.defineProperty(this, 'paused', { configurable: true, get: () => false }); return Promise.resolve(); });
    pause = jest.spyOn(window.HTMLMediaElement.prototype, 'pause').mockImplementation(function () {
      Object.defineProperty(this, 'paused', { configurable: true, get: () => true }); });
  });
  afterEach(() => { play.mockRestore(); pause.mockRestore(); });

  test('bloc affiché HORS confirmation (espace) : AUCUNE lecture automatique, écouter / pause / reprendre', async () => {
    global.fetch = jest.fn((url) => (String(url).includes('/api/invitation/suivi') ? reponse({}) : reponse(DETAILS)));
    await act(async () => { render(<InviterMesAmis relaisInitial={RELAIS} />); });
    await attendre(() => expect(q('afroboosteur-titre').textContent).toMatch(/Deviens Afroboosteur/));
    // V610m : le texte de la boule de neige
    expect(q('afroboosteur-texte').textContent).toBe('Fais circuler l’énergie. Invite tes amis à vivre Afroboost avec toi.');
    const a = q('afroboosteur-audio');
    expect(a.autoplay).toBe(false);
    expect(a.getAttribute('preload')).toBe('none');
    expect(a.getAttribute('src')).toBe('/api/files/a1/afroboosteur.mp3');
    expect(play).not.toHaveBeenCalled();
    expect(q('afroboosteur-ecouter').textContent).toMatch(/Écouter le message/);
    await act(async () => { q('afroboosteur-ecouter').click(); });
    expect(play).toHaveBeenCalledTimes(1);
    expect(q('afroboosteur-ecouter').textContent).toMatch(/Pause/);
    await act(async () => { q('afroboosteur-ecouter').click(); });
    expect(pause).toHaveBeenCalledTimes(1);
    expect(q('afroboosteur-ecouter').textContent).toMatch(/Reprendre le message/);
    await act(async () => { q('afroboosteur-ecouter').click(); });
    expect(play).toHaveBeenCalledTimes(2);
  });

  test('« Inviter mes amis » : WhatsApp avec le lien PERSONNEL, suivi « partage déclenché » (jamais « envoyé »)', async () => {
    global.fetch = jest.fn((url) => (String(url).includes('/api/invitation/suivi') ? reponse({}) : reponse(DETAILS)));
    const ouvert = jest.spyOn(window, 'open').mockImplementation(() => null);
    await act(async () => { render(<InviterMesAmis relaisInitial={RELAIS} />); });
    await attendre(() => expect(q('afroboosteur-titre')).toBeTruthy());
    expect(q('inviter-partager').textContent).toMatch(/Inviter mes amis/);       // V610o
    await act(async () => { q('inviter-partager').click(); });
    expect(q('inviter-whatsapp').textContent).toMatch(/WhatsApp/);
    await act(async () => { q('inviter-whatsapp').click(); });
    const url = decodeURIComponent(ouvert.mock.calls[0][0]);
    expect(url).toMatch(/wa\.me|whatsapp/);
    expect(url).toMatch(/afroboost\.com\/i\/JetonSophie123456/);
    // V610o : message de l'AFROBOOSTEUR (billet payé), son lien perso.
    // V618L : plus de « 50 PLACES » inventé — la ligne n'existe que si le serveur l'envoie (capacité réelle).
    expect(url).toMatch(/🔥 Je deviens Afroboosteur !/);
    expect(url).toMatch(/Je vais à Afroboost Silent — Édition Spéciale 🎧/);
    expect(url).not.toMatch(/50 PLACES/);
    expect(url).not.toMatch(/gratuit/i);
    const suivi = global.fetch.mock.calls.filter((c) => String(c[0]).includes('/api/invitation/suivi'));
    expect(JSON.parse(suivi[suivi.length - 1][1].body).evenement).toBe('partage_whatsapp_declenche');
    expect(document.body.textContent).not.toMatch(/envoyé/i);
    ouvert.mockRestore();
  });

  test('V610m — confirmation (`autoLecture`) : UNE tentative de lecture, jamais en boucle ; refus -> « Écouter le message »', async () => {
    global.fetch = jest.fn((url) => (String(url).includes('/api/invitation/suivi') ? reponse({}) : reponse(DETAILS)));
    play.mockImplementation(() => Promise.reject(new Error('NotAllowedError')));
    await act(async () => { render(<InviterMesAmis relaisInitial={RELAIS} autoLecture />); });
    await attendre(() => expect(play).toHaveBeenCalledTimes(1));
    await act(async () => { await new Promise((r) => setTimeout(r, 60)); });
    expect(play).toHaveBeenCalledTimes(1);                       // une seule tentative
    const a = q('afroboosteur-audio');
    expect(a.loop).toBe(false);
    expect(a.autoplay).toBe(false);
    expect(q('afroboosteur-ecouter').textContent).toMatch(/Écouter le message/);
    expect(q('inviter-partager').textContent).toMatch(/Inviter mes amis/);
  });

  test('V610m — événement PAYANT sans audio configuré : même bloc « Deviens Afroboosteur » (gros bouton), aucun lecteur', async () => {
    global.fetch = jest.fn(() => reponse({ ...DETAILS, audio_partage_url: null }));
    await act(async () => { render(<InviterMesAmis relaisInitial={RELAIS} autoLecture />); });
    await attendre(() => expect(q('afroboosteur-titre')).toBeTruthy());
    expect(document.querySelector('audio')).toBeNull();
    expect(q('inviter-partager').textContent).toMatch(/Inviter mes amis/);
    expect(document.body.textContent).toMatch(/Copier mon lien/);
  });

  test('événement GRATUIT : bloc d\'invitation habituel, aucun audio', async () => {
    global.fetch = jest.fn(() => reponse({ ...DETAILS, type: 'event_free' }));
    await act(async () => { render(<InviterMesAmis relaisInitial={RELAIS} />); });
    await attendre(() => expect(q('inviter-mes-amis')).toBeTruthy());
    expect(q('afroboosteur-titre')).toBeNull();
    expect(document.querySelector('audio')).toBeNull();
  });

  test('page AVANT achat (/i/) : la vidéo, jamais l\'audio Afroboosteur', async () => {
    global.fetch = jest.fn((url) => (String(url).includes('/api/invitation/publique/')
      ? reponse({ ...DETAILS, video_url: '/api/files/v1/silent.mp4', cible: '/?offre=o&inv=T' }) : reponse({})));
    await act(async () => { render(<InvitationPublique token="T123456789012345678" />); });
    await attendre(() => expect(q('inv-pub-video')).toBeTruthy());
    expect(document.querySelector('audio')).toBeNull();
    expect(document.body.innerHTML).not.toMatch(/afroboosteur/i);
  });
});

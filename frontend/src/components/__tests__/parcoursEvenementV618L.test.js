/**
 * V618L — PARCOURS ÉVÉNEMENT SIMPLIFIÉ + PARCOURS MEMBRE CORRIGÉ (reproduits d'abord avec Playwright).
 *   - page publique : ordre VIDÉO -> PROMESSE -> DATE/LIEU -> PRIX -> CTA (avec le prix) -> MEMBRE -> LIRE PLUS ;
 *   - membre : une étape e-mail sur place -> « Lien d'accès envoyé » + Renvoyer / Changer d'adresse ;
 *   - « Voir l'événement » de l'espace : jamais l'accueil ;
 *   - plus de faux « 50 PLACES » ; « 30 CHF dès le mercredi 21 octobre à 18h45 ».
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn(), create: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } }));
// eslint-disable-next-line import/first
import axios from 'axios';
// eslint-disable-next-line import/first
import InvitationPublique, { libelleCta, jourBascule, PROMESSE_EVENEMENT } from '../InvitationPublique';
// eslint-disable-next-line import/first
import { DemandeLienMembre } from '../AccesMembreEvenement';
// eslint-disable-next-line import/first
import EvenementsOfferts, { quandEvenementLigne } from '../EvenementsOfferts';
// eslint-disable-next-line import/first
import InviterMesAmis from '../InviterMesAmis';
// eslint-disable-next-line import/first
import { lienVoirEvenement } from '../../utils/voirEvenement';
// eslint-disable-next-line import/first
import { texteAmbassadeur } from '../../utils/invitationCampagne';
// eslint-disable-next-line import/first
import { retenirIntentionMembre } from '../../utils/participationEvenement';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
// V618M : la carte événement lit les conditions publiées AU MOMENT de réserver (aucune ici).
beforeEach(() => { axios.get.mockResolvedValue({ data: { required: false } }); });
let conteneur = null;
let racine = null;
function rendre(el) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  racine.render(el);
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
const json = (corps, ok = true, status = 200) => Promise.resolve({ ok, status, json: () => Promise.resolve(corps) });
async function attendre(fn) {
  let derniere;
  for (let i = 0; i < 40; i += 1) {
    try { fn(); return; } catch (e) { derniere = e; }
    // eslint-disable-next-line no-await-in-loop
    await act(async () => { await new Promise((r) => setTimeout(r, 25)); });
  }
  throw derniere;
}

const SILENT = {
  type: 'event_paid', title: 'AFROBOOST SILENT — ÉDITION SPÉCIALE', offer_id: 'OFF-1', offre_nom: 'AFROBOOST SILENT — ÉDITION SPÉCIALE',
  date_label: 'mercredi 28 octobre', time_label: '18:45', lieu: 'Chemin des Valangines 97, 2000 Neuchâtel',
  inviter_display: { prenom: 'Bassi' }, gratuit_membres: true, message_places: null,
  description: 'Afroboost Silent\n\n25 CHF prévente',
  reservation_directe: { offer_id: 'OFF-1' },
  prix_actif: { prix: 25, palier: 'early_bird', libelle: 'Prévente',
    paliers: [{ palier: 'early_bird', libelle: 'Prévente', prix: 25, actif: true, jusqu_a: '2026-10-21T16:45:00+00:00' },
      { palier: 'standard', libelle: 'Standard', prix: 30, actif: false, jusqu_a: '2026-10-27T17:45:00+00:00' },
      { palier: 'last_minute', libelle: 'Dernière minute', prix: 40, actif: false }],
    prochain: { palier: 'standard', prix: 30, a_partir_de: '2026-10-21T16:45:00+00:00' } },
};

describe('V618L — page publique de l’événement', () => {
  test('ordre VIDÉO -> PROMESSE -> DATE/LIEU -> PRIX -> CTA -> MEMBRE -> LIRE PLUS, sans répétition ni faux compteur', async () => {
    global.fetch = jest.fn((url) => (String(url).includes('/api/invitation/publique/') ? json(SILENT) : json({})));
    await act(async () => { rendre(<InvitationPublique token="TOKENSILENT12345678" />); });
    await attendre(() => expect(q('inv-pub-titre')).toBeTruthy());
    const ordre = ['inv-pub-titre', 'inv-pub-accroche', 'inv-pub-date', 'inv-pub-prix-actif', 'inv-pub-cta', 'inv-pub-membre-compact', 'inv-pub-lire-plus'];
    const elems = ordre.map((id) => q(id));
    elems.forEach((e, i) => expect([ordre[i], !!e]).toEqual([ordre[i], true]));
    for (let i = 1; i < elems.length; i += 1) {
      // eslint-disable-next-line no-bitwise
      expect(elems[i - 1].compareDocumentPosition(elems[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
    expect(q('inv-pub-accroche').textContent).toBe(PROMESSE_EVENEMENT);
    expect(q('inv-pub-cta').textContent).toBe('Je réserve ma place — 25 CHF');
    expect(q('inv-pub-urgence').textContent).toBe('30 CHF dès le mercredi 21 octobre à 18h45.');
    const texte = document.body.textContent;
    expect(texte).not.toMatch(/novembre/);
    expect(texte).not.toMatch(/50 PLACES/i);
    expect(q('inv-pub-places')).toBeNull();
    expect(q('inv-pub-groupe')).toBeNull();
    expect(texte.match(/25 CHF/g)).toHaveLength(2);                  // le prix + le bouton, rien d'autre hors « Lire plus »
    expect(document.querySelectorAll('[data-testid^="inv-pub-palier-"]')).toHaveLength(0);
    // UN seul bouton de réservation (plus de barre fixe en double pour l'événement payant)
    expect(document.querySelectorAll('[data-testid="inv-pub-cta"]')).toHaveLength(1);
  });

  test('« Lire plus » garde les conditions de prix (avec l’heure) ; jamais le bloc membre', async () => {
    global.fetch = jest.fn((url) => (String(url).includes('/api/invitation/publique/') ? json(SILENT) : json({})));
    await act(async () => { rendre(<InvitationPublique token="TOKENSILENT12345678" />); });
    await attendre(() => expect(q('inv-pub-lire-plus')).toBeTruthy());
    await act(async () => { q('inv-pub-lire-plus').click(); });
    const plus = q('inv-pub-lire-plus-contenu').textContent;
    expect(plus).toMatch(/Prévente 25 CHF jusqu'au 21 octobre à 18h45 · Standard 30 CHF jusqu'au 27 octobre à 18h45 · Dernière minute 40 CHF/);
    expect(plus).not.toMatch(/Réserver ma place offerte|Recevoir mon lien/);
  });

  test('« 50 PLACES » s’affiche seulement si le serveur l’envoie (capacité réelle)', async () => {
    global.fetch = jest.fn((url) => (String(url).includes('/api/invitation/publique/') ? json(Object.assign({}, SILENT, { message_places: '50 PLACES' })) : json({})));
    await act(async () => { rendre(<InvitationPublique token="TOKENSILENT12345678" />); });
    await attendre(() => expect(q('inv-pub-places').textContent).toMatch(/50 PLACES/));
  });

  test('membre : l’étape e-mail s’ouvre SUR PLACE, puis « Lien d’accès envoyé » + Renvoyer / Changer d’adresse ; le lien porte l’événement', async () => {
    const appels = [];
    global.fetch = jest.fn((url, opt) => {
      appels.push([String(url), opt]);
      if (String(url).includes('/api/invitation/publique/')) return json(SILENT);
      if (String(url).includes('/api/subscriber/recover')) return json({ success: true });
      return json({});
    });
    await act(async () => { rendre(<InvitationPublique token="TOKENSILENT12345678" />); });
    await attendre(() => expect(q('inv-pub-membre-compact')).toBeTruthy());
    expect(q('membre-lien')).toBeNull();
    await act(async () => { q('inv-pub-membre-compact').click(); });
    expect(q('membre-lien').textContent).toMatch(/Entre l'adresse e-mail liée à ton abonnement Afroboost\./);
    const champ = q('membre-lien-email');
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(champ, 'Membre@Exemple.ch');
      champ.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => { q('membre-lien-envoyer').click(); });
    await attendre(() => expect(q('membre-lien-envoye')).toBeTruthy());
    expect(q('membre-lien-envoye').textContent).toMatch(/Lien d'accès envoyé/);
    expect(q('membre-lien-envoye').textContent).toMatch(/Ouvre l'e-mail Afroboost que nous venons de t'envoyer et touche « Accéder à mon espace »\./);
    expect(document.body.textContent).not.toMatch(/Gmail/);
    const corps = JSON.parse(appels.find(([u]) => u.includes('/api/subscriber/recover'))[1].body);
    expect(corps).toEqual({ email: 'membre@exemple.ch', offre: 'OFF-1', jeton: 'TOKENSILENT12345678' });
    await act(async () => { q('membre-lien-renvoyer').click(); });
    await attendre(() => expect(q('membre-lien-renvoye')).toBeTruthy());
    expect(appels.filter(([u]) => u.includes('/api/subscriber/recover'))).toHaveLength(2);
    await act(async () => { q('membre-lien-changer').click(); });
    expect(q('membre-lien-email')).toBeTruthy();
    // aucun paiement, aucune réservation depuis la page publique pour le membre
    expect(appels.some(([u]) => u.includes('/api/create-checkout-session') || u.includes('/offert'))).toBe(false);
  });
});

describe('V618L — DemandeLienMembre', () => {
  test('même écran pour toute adresse (rien ne dit qui est membre) ; un 429 au renvoi GARDE l’écran envoyé', async () => {
    let n = 0;
    global.fetch = jest.fn(() => { n += 1; return n === 1 ? json({ success: true }) : json({ detail: 'Trop' }, false, 429); });
    await act(async () => { rendre(<DemandeLienMembre offreVisee="OFF-1" jetonInvitation="TOKENSILENT12345678" />); });
    const champ = q('membre-lien-email');
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(champ, 'inconnu@exemple.ch');
      champ.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => { q('membre-lien-envoyer').click(); });
    await attendre(() => expect(q('membre-lien-envoye')).toBeTruthy());
    await act(async () => { q('membre-lien-renvoyer').click(); });
    await attendre(() => expect(q('membre-lien-erreur')).toBeTruthy());
    expect(q('membre-lien-envoye')).toBeTruthy();
    expect(q('membre-lien-erreur').textContent).toMatch(/Trop de demandes/);
  });

  test('adresse invalide : aucun appel', async () => {
    global.fetch = jest.fn(() => json({}));
    await act(async () => { rendre(<DemandeLienMembre />); });
    await act(async () => { q('membre-lien-envoyer').click(); });
    expect(global.fetch).not.toHaveBeenCalled();
    expect(document.body.textContent).toMatch(/Adresse e-mail invalide/);
  });
});

describe('V618L — espace membre', () => {
  test('« Voir l’événement » : place offerte -> sa carte ; sinon la page de l’événement ; jamais l’accueil quand on sait mieux', () => {
    const occ = { offer_id: 'OFF-1', lien_evenement: '/i/EQiBPuqSmrn7b1cKjybkTTEz88Wlz4cs' };
    expect(lienVoirEvenement(occ, { evenements_offerts: [{ offer_id: 'OFF-1' }] })).toBe('#evt-offert-OFF-1');
    expect(lienVoirEvenement(occ, { evenements_offerts: [] })).toBe('/i/EQiBPuqSmrn7b1cKjybkTTEz88Wlz4cs');
    expect(lienVoirEvenement({ offer_id: 'OFF-1', lien_evenement: 'https://evil.example/x' }, {})).toBe('/?offre=OFF-1');
    expect(lienVoirEvenement({ offer_id: 'OFF-1', lien_evenement: '/i/<script>' }, {})).toBe('/?offre=OFF-1');
  });

  test('carte offerte : « Ta place est offerte avec ton abonnement » -> réservée : titre, date, ville, Inviter mes amis, Copier, Voir ma réservation', async () => {
    const axios = require('axios');
    axios.post.mockResolvedValue({ data: { success: true, prix: 0, relais: { jeton: 'JetonMembre12345678', share_url: 'https://afroboost.com/i/JetonMembre12345678' } } });
    global.fetch = jest.fn((url) => (String(url).includes('/api/invitation/publique/') ? json(SILENT) : json({})));
    const EVT = { offer_id: 'OFF-1', titre: 'AFROBOOST SILENT — ÉDITION SPÉCIALE', datetime: '2026-10-28T18:45:00', lieu: 'Chemin des Valangines 97, 2000 Neuchâtel', deja_reserve: false };
    await act(async () => { rendre(<EvenementsOfferts evenements={[EVT]} accessCode="AFR-M1" memberSlug="" />); });
    expect(q('evt-offert-avantage').textContent).toBe('PLACE OFFERTE');   // V618M : « Ton avantage membre · PLACE OFFERTE »
    expect(document.getElementById('evt-offert-OFF-1')).toBeTruthy();   // l'ancre de « Voir l'événement »
    await act(async () => { q('evt-offert-reserver').click(); });
    await attendre(() => expect(q('evt-offert-confirme-titre').textContent).toBe('Ta place est réservée !'));
    expect(String(axios.post.mock.calls[0][0])).toMatch(/\/evenement\/OFF-1\/offert$/);   // 0 CHF, aucun Stripe
    expect(q('evt-offert-quand').textContent).toBe('Mercredi 28 octobre · 18h45');
    expect(q('evt-offert-ville').textContent).toBe('Neuchâtel');
    expect(document.body.textContent.split('Ta place est réservée').length - 1).toBe(1);   // jamais deux fois
    await attendre(() => expect(q('afroboosteur-titre')).toBeTruthy());
    expect(q('inviter-partager').textContent).toMatch(/Inviter mes amis/);
    expect(q('inviter-copier-direct').textContent).toMatch(/Copier mon lien/);
    expect(q('voir-ma-reservation').textContent).toMatch(/Voir ma réservation/);
  });

  test('membre déjà inscrit : « Ta place est déjà réservée » + invitation (aucune 2e réservation)', async () => {
    const axios = require('axios');
    axios.post.mockResolvedValue({ data: { success: true, deja: true, relais: { jeton: 'JetonMembre12345678', share_url: 'https://afroboost.com/i/JetonMembre12345678' } } });
    global.fetch = jest.fn((url) => (String(url).includes('/api/invitation/publique/') ? json(SILENT) : json({})));
    retenirIntentionMembre('OFF-1', 'TOKENSILENT12345678');   // arrivé par le lien de l'e-mail (événement visé)
    const EVT = { offer_id: 'OFF-1', titre: 'AFROBOOST SILENT', datetime: '2026-10-28T18:45:00', lieu: 'Neuchâtel', deja_reserve: true };
    await act(async () => { rendre(<EvenementsOfferts evenements={[EVT]} accessCode="AFR-M1" memberSlug="" />); });
    await attendre(() => expect(q('inviter-mes-amis')).toBeTruthy());
    expect(document.body.textContent).toMatch(/Ta place est déjà réservée/);
    expect(q('evt-offert-reserver')).toBeNull();
  });

  test('date en une ligne majuscule', () => {
    expect(quandEvenementLigne('2026-10-28T18:45:00')).toBe('Mercredi 28 octobre · 18h45');
  });
});

describe('V618L — utilitaires', () => {
  test('bouton : le prix ACTUEL dans le libellé, jamais deux fois « CHF »', () => {
    expect(libelleCta({}, { prix: 25 })).toBe('Je réserve ma place — 25 CHF');
    expect(libelleCta({ cta_label: 'Je prends ma place' }, { prix: 30 })).toBe('Je prends ma place — 30 CHF');
    expect(libelleCta({ cta_label: 'Réserver — 25 CHF' }, { prix: 25 })).toBe('Réserver — 25 CHF');
    expect(libelleCta({}, null)).toBe('Je réserve ma place');
  });
  test('bascule : jour ET heure de Zurich', () => {
    expect(jourBascule('2026-10-21T16:45:00+00:00')).toBe('mercredi 21 octobre à 18h45');
    expect(jourBascule('2026-10-27T17:45:00+00:00')).toBe('mardi 27 octobre à 18h45');
  });
  test('message WhatsApp : aucun « 50 PLACES » par défaut ; présent seulement s’il est fourni', () => {
    const dto = { title: 'AFROBOOST SILENT — ÉDITION SPÉCIALE', share_url: 'https://afroboost.com/i/X', date_label: 'mercredi 28 octobre', time_label: '18:45', lieu: 'Valangines, 2000 Neuchâtel' };
    expect(texteAmbassadeur(dto, {})).not.toMatch(/50 PLACES/);
    expect(texteAmbassadeur(dto, { messagePlaces: null })).not.toMatch(/PLACES/);
    expect(texteAmbassadeur(dto, { messagePlaces: '50 PLACES' })).toMatch(/🔥 50 PLACES/);
  });
});

describe('V618L — l’ami du membre', () => {
  test('lien personnel d’un membre : prix public, aucune gratuité héritée', async () => {
    const AMI = Object.assign({}, SILENT, { inviter_display: { prenom: 'Membre' }, gratuit_membres: true });
    global.fetch = jest.fn((url) => (String(url).includes('/api/invitation/publique/') ? json(AMI) : json({})));
    await act(async () => { rendre(<InvitationPublique token="JetonMembre12345678" />); });
    await attendre(() => expect(q('inv-pub-prix-actif')).toBeTruthy());
    expect(q('inv-pub-inviteur').textContent).toBe("Membre t'invite à Afroboost Silent");
    expect(q('inv-pub-prix-actif').textContent).toBe('25 CHF');
    expect(q('inv-pub-cta').textContent).toBe('Je réserve ma place — 25 CHF');
    expect(document.body.textContent).not.toMatch(/Ta place est offerte|offert pour toi|(^|[^0-9])0 CHF|gratuit/i);
  });
});

describe('V618L — InviterMesAmis', () => {
  test('« Voir ma réservation » seulement si une action est fournie', async () => {
    global.fetch = jest.fn(() => json(SILENT));
    const RELAIS = { jeton: 'JetonMembre12345678', share_url: 'https://afroboost.com/i/JetonMembre12345678' };
    await act(async () => { rendre(<InviterMesAmis relaisInitial={RELAIS} />); });
    await attendre(() => expect(q('afroboosteur-titre')).toBeTruthy());
    expect(q('voir-ma-reservation')).toBeNull();
  });
});

/**
 * V610e — l'éditeur complet d'invitation : décisions pures, rendu, enregistrement,
 * confirmation si des participants existent, aperçu (sans réseau), « Détails ».
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn(), create: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } }));
jest.mock('../InvitationMiniature', () => function Mini() { return null; });
// eslint-disable-next-line import/first
import axios from 'axios';
// eslint-disable-next-line import/first
import EditeurInvitation from '../EditeurInvitation';
// eslint-disable-next-line import/first
import InvitationPublique from '../../InvitationPublique';
// eslint-disable-next-line import/first
import { changementsEvenement, estSensible, erreurTarifs, quandLisible, genreFichier } from '../../../utils/invitationEdition';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let conteneur = null; let racine = null;
function render(el) { conteneur = document.createElement('div'); document.body.appendChild(conteneur); racine = createRoot(conteneur); racine.render(el); return { container: conteneur }; }
afterEach(() => { if (racine) act(() => racine.unmount()); if (conteneur) conteneur.remove(); racine = null; conteneur = null; jest.clearAllMocks(); delete global.fetch; });
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
async function attendre(fn) { let e; for (let i = 0; i < 40; i += 1) { try { fn(); return; } catch (x) { e = x; } await act(async () => { await new Promise((r) => setTimeout(r, 25)); }); } throw e; }
function saisir(el, valeur) {
  const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, valeur);
  el.dispatchEvent(new Event('input', { bubbles: true }));
}

const EVT = { date: '2026-10-28', heure: '18:45', lieu: 'Chem. des Valangines 97, 2000 Neuchâtel', date_modifiable: true,
  tarifs: { prevente: 25, standard: 30, derniere_minute: 40, libelles: { prevente: 'Prévente', standard: 'Standard', derniere_minute: 'Dernière minute' },
    fin_prevente: '2026-10-21T18:45', fin_standard: '2026-10-27T18:45', debut_evenement: '2026-10-28T18:45', prix_actif: 25, palier_actif: 'early_bird' },
  membres: { configuree: true, actif: true, libelle: 'Avantages membres' }, participants: { reservations: 2, paiements: 2 },
  // V618M : avantages par offre (identifiants réels) + urgence / capacité séparées
  avantages: { actif: true, regles: [{ offer_id: 'ba530ae4', nom: 'Membres — 8 mois', type: 'gratuit', valeur: null, active: true }],
    offres: [{ id: 'ba530ae4', nom: 'Membres — 8 mois' }, { id: '7764d100', nom: 'Étudiant' }], autres: [{ id: 'a687ce86', nom: 'PULSE x10 cours' }] },
  urgence: { texte: '50 PLACES', visible: false, capacite_limitee: false, capacite_max: null, places_prises: 2 },
  description_offre: 'Afroboost Silent…' };
const INV = { id: 'C1', type: 'event_paid', status: 'active', title: 'AFROBOOST SILENT', subtitle: 'Accroche', description: null, message: null,
  cta_label: 'Je réserve ma place', image_url: null, image_source: 'default', video_url: '/api/files/v1/silent.mp4', audio_url: null,
  audio_partage_url: '/api/files/a1/afroboosteur.mp3', share_url: 'https://afroboost.com/i/TOK', share_token: 'TOK', version: 3,
  inviter_display: { prenom: 'Bassi' }, date_label: 'mercredi 28 octobre', time_label: '18:45', lieu: EVT.lieu, gratuit_membres: true,
  prix_actif: { prix: 25, palier: 'early_bird', libelle: 'Prévente', paliers: [] } };

describe('V610e — décisions pures', () => {
  test('changements : seulement ce qui change ; sensible = date/heure/lieu/prix', () => {
    const f = { date: '2026-10-28', heure: '19:00', lieu: EVT.lieu, prevente: '27', standard: '30', derniere_minute: '40', fin_prevente: EVT.tarifs.fin_prevente, fin_standard: EVT.tarifs.fin_standard, membres_actif: true };
    const c = changementsEvenement(f, EVT);
    expect(c).toEqual({ heure: '19:00', prevente: 27 });
    expect(estSensible(c)).toBe(true);
    expect(estSensible(changementsEvenement(Object.assign({}, f, { heure: '18:45', prevente: '25' }), EVT))).toBe(false);
    expect(estSensible(changementsEvenement(Object.assign({}, f, { heure: '18:45', prevente: '25', membres_actif: false }), EVT))).toBe(true);
  });
  test('tarifs : montants positifs et chronologie', () => {
    const base = { prevente: '25', standard: '30', derniere_minute: '40', fin_prevente: '2026-10-21T18:45', fin_standard: '2026-10-27T18:45', date: '2026-10-28', heure: '18:45' };
    expect(erreurTarifs(base, EVT)).toBe('');
    expect(erreurTarifs(Object.assign({}, base, { standard: '-1' }), EVT)).toMatch(/positifs/);
    expect(erreurTarifs(Object.assign({}, base, { fin_prevente: '2026-10-28T10:00' }), EVT)).toMatch(/prévente doit finir/);
    expect(erreurTarifs(Object.assign({}, base, { fin_standard: '2026-10-29T10:00' }), EVT)).toMatch(/au plus tard/);
  });
  test('lisible + genres de fichiers acceptés', () => {
    expect(quandLisible('2026-10-21T18:45')).toBe('mercredi 21 octobre · 18h45');
    expect(genreFichier({ type: 'video/mp4' }, 'video')).toBe('video');
    expect(genreFichier({ type: 'audio/mpeg' }, 'audio')).toBe('audio');
    expect(genreFichier({ type: 'text/html' }, 'video')).toBe('');
    expect(genreFichier({ type: 'image/svg+xml' }, 'audio')).toBe('');
  });
});

describe('V610e — EditeurInvitation', () => {
  beforeEach(() => {
    axios.get.mockImplementation((url) => (String(url).includes('/campaigns-edition/')
      ? Promise.resolve({ data: { invitation: INV, evenement: EVT } }) : Promise.resolve({ data: { items: [] } })));
  });

  test('sections repliables (une ouverte), libellés des deux audios, mention membres, aucune capacité', async () => {
    await act(async () => { render(<EditeurInvitation invitationId="C1" onClose={() => {}} />); });
    await attendre(() => expect(q('ed-titre').value).toBe('AFROBOOST SILENT'));
    expect(q('edit-section-contenu-titre').getAttribute('aria-expanded')).toBe('true');
    await act(async () => { q('edit-section-medias-titre').click(); });
    expect(q('edit-section-contenu-titre').getAttribute('aria-expanded')).toBe('false');
    expect(document.body.textContent).toMatch(/Message audio avant réservation/);
    expect(document.body.textContent).toMatch(/Message audio après réservation \/ partage/);
    expect(document.body.textContent).toMatch(/Deviens Afroboosteur/);
    expect(document.body.textContent).not.toMatch(/Audio 1|Audio 2|Afrobooster\b/);
    expect(q('ed-video-actuel').getAttribute('preload')).toBe('metadata');   // V610k : « none » = cadre noir (cause du bug « Voir »)
    expect(q('ed-video-actuel').autoplay).toBe(false);
    await act(async () => { q('edit-section-tarifs-titre').click(); });
    expect(q('ed-tarif-actif').textContent).toMatch(/25 CHF/);
    // V618M : les avantages membres ont leur section (plus de « 8 mois » écrit en dur)
    await act(async () => { q('edit-section-avantages-titre').click(); });
    expect(q('ed-membres').textContent).toMatch(/Avantages membres actifs/);
    expect(document.body.textContent).not.toMatch(/8 mois actifs/);
    expect(document.body.textContent).not.toMatch(/\/api\/files\/|9fa5ac00|ba530ae4|50 places|places maximum/i);
  });

  test('enregistrer un titre -> PUT invitation (liste blanche), rien sur l’événement', async () => {
    axios.put.mockResolvedValue({ data: {} });
    await act(async () => { render(<EditeurInvitation invitationId="C1" onClose={() => {}} />); });
    await attendre(() => expect(q('ed-titre')).toBeTruthy());
    await act(async () => { saisir(q('ed-titre'), 'Nouveau titre'); });
    await act(async () => { q('ed-enregistrer').click(); });
    await attendre(() => expect(axios.put).toHaveBeenCalled());
    const [url, corps] = axios.put.mock.calls[0];
    expect(url).toMatch(/\/api\/referral\/campaigns\/C1$/);
    expect(corps).toEqual({ title: 'Nouveau titre' });
  });

  test('prix modifié avec participants -> confirmation, puis renvoi avec confirmer: true', async () => {
    axios.put.mockImplementation((url, corps) => {
      if (String(url).includes('/evenement') && corps && corps.simuler) return Promise.resolve({ data: { simulation: true, prix_actif: 27, palier_actif: 'early_bird', tarifs: Object.assign({}, EVT.tarifs, { prevente: 27, prix_actif: 27 }) } });
      if (String(url).includes('/evenement') && !(corps && corps.confirmer)) return Promise.reject({ response: { status: 409, data: { detail: { code: 'confirmation_requise', message: 'Des participants ont déjà réservé cet événement. Continuer ?' } } } });
      return Promise.resolve({ data: {} });
    });
    await act(async () => { render(<EditeurInvitation invitationId="C1" onClose={() => {}} />); });
    await attendre(() => expect(q('ed-titre')).toBeTruthy());
    await act(async () => { q('edit-section-tarifs-titre').click(); });
    await act(async () => { saisir(q('ed-prix-prevente'), '27'); });
    await act(async () => { q('ed-enregistrer').click(); });
    await attendre(() => expect(q('ed-confirmation')).toBeTruthy());
    expect(q('ed-confirmation').textContent).toMatch(/déjà réservé/);
    await act(async () => { q('ed-confirmation-continuer').click(); });
    await attendre(() => expect(axios.put.mock.calls.some(([u, c]) => String(u).includes('/evenement') && c && c.confirmer === true && c.prevente === 27)).toBe(true));
  });
});

describe('V610e — aperçu et « Détails »', () => {
  test('aperçu : AUCUN appel réseau, aucun suivi, bouton inerte ; description repliée', async () => {
    global.fetch = jest.fn();
    const assign = jest.fn();
    await act(async () => { render(<InvitationPublique apercu={Object.assign({}, INV, { description: 'Ligne 1\nLigne 2' })} token="apercu" />); });
    expect(global.fetch).not.toHaveBeenCalled();
    expect(q('inv-pub-titre').textContent).toBe('AFROBOOST SILENT');
    expect(q('inv-pub-description')).toBeNull();
    await act(async () => { q('inv-pub-lire-plus').click(); });
    expect(q('inv-pub-description').textContent).toBe('Ligne 1\nLigne 2');
    const avant = window.location.href;
    await act(async () => { q('inv-pub-cta').click(); });
    expect(window.location.href).toBe(avant);
    expect(global.fetch).not.toHaveBeenCalled();
    expect(assign).not.toHaveBeenCalled();
  });
});

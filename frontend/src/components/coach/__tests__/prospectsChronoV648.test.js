// V648 — onglet « Prospects » : « Derniers envois », « Brouillons », tri et période.
//
// CE QUI EST PROUVÉ ICI :
//   * les quatre commandes sont VISIBLES d'emblée, sans ouvrir de menu ;
//   * chacune part au SERVEUR (donc s'applique aux 471 fiches, pas aux 25
//     affichées) ;
//   * « Derniers envois » s'appuie sur la date d'envoi réelle, et son état vide
//     dit « aucun envoi » — pas « aucun prospect » ;
//   * la période est calculée en heure de Neuchâtel et envoyée en instants
//     absolus ;
//   * l'écran sans ces commandes est inchangé (aucun paramètre en plus).
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import ProspectsSection from '../ProspectsSection';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), patch: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));

const SECTION = { ATTENTE: 'attente', CHARGEMENT: 'chargement', OK: 'ok', ERREUR: 'erreur', SESSION: 'session' };
let mockEtatPilote = { etat: SECTION.OK, donnees: null };
let mockDerniereSource = null;

jest.mock('../../../hooks/useChargement', () => ({
  __esModule: true,
  SECTION: { ATTENTE: 'attente', CHARGEMENT: 'chargement', OK: 'ok', ERREUR: 'erreur', SESSION: 'session' },
  default: (sources) => {
    mockDerniereSource = sources.prospects;
    const sections = {};
    Object.keys(sources).forEach((cle) => { sections[cle] = mockEtatPilote; });
    return { sections, reessayer: jest.fn() };
  },
}));
jest.mock('../../../hooks/useNichesProspection', () => ({ __esModule: true, default: () => ({ niches: [] }) }));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

let conteneur; let racine;
async function monter() {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(<ProspectsSection API="/api" />); });
}
afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
  jest.clearAllMocks();
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const texte = () => conteneur.textContent;

const prospect = (sur) => Object.assign({
  id: 'p1', ref: 'X-01', organisation_name: 'Studio Test', city: 'Neuchâtel', category: 'danse',
  status: 'a_contacter', priority: 'B', score: 5, niche_id: null, created_at: '2026-11-01T10:00:00+00:00',
}, sur || {});
const reponse = (prospects, total) => ({
  total: total === undefined ? prospects.length : total,
  returned: prospects.length, limit: 25, offset: 0,
  counts: { a_contacter: 0, contacte: 0, repondu: 0, interesse: 0, partenaire: 0, refus: 0,
    exclu: 0, pause: 0, accepte: 0, candidature: 0, adresse_a_corriger: 0, total: 471, corbeille: 0 },
  prospects,
});

async function changer(id, valeur) {
  await act(async () => {
    const el = par(id);
    const proto = el.tagName === 'SELECT' ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, valeur);
    el.dispatchEvent(new Event('change', { bubbles: true }));
  });
}
async function cliquer(id) { await act(async () => { par(id).click(); }); }

/** Les paramètres RÉELLEMENT envoyés au serveur après une action d'écran. */
async function paramsApres(action) {
  mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()], 471) };
  await monter();
  if (action) await action();
  axios.get.mockResolvedValue({ data: reponse([]) });
  await act(async () => { await mockDerniereSource.appel(); });
  const appel = axios.get.mock.calls.find((c) => String(c[0]).indexOf('/partner-prospects') !== -1);
  if (!appel) throw new Error('aucun appel à /partner-prospects');
  return appel[1].params;
}

test('les quatre commandes sont visibles d’emblée, sans menu à ouvrir', async () => {
  mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()], 471) };
  await monter();
  expect(par('prospects-chrono')).not.toBeNull();
  expect(par('prospects-derniers-envois')).not.toBeNull();
  expect(par('prospects-brouillons')).not.toBeNull();
  expect(par('prospects-tri')).not.toBeNull();
  expect(par('prospects-periode')).not.toBeNull();
  // Elles ne sont pas enfermées dans un <details>.
  expect(par('prospects-chrono').closest('details')).toBeNull();
  expect(par('prospects-chrono-total').textContent).toContain('471');
});

test('sans commande active, la requête est EXACTEMENT celle d’avant V648', async () => {
  const params = await paramsApres(null);
  expect(Object.keys(params).sort()).toEqual(['limit', 'offset']);
});

test('« Derniers envois » demande au serveur les envois réels, triés du plus récent', async () => {
  const params = await paramsApres(() => cliquer('prospects-derniers-envois'));
  expect(params.envoyes).toBe('1');
  expect(params.tri).toBe('envoi_recent');
  expect(params.brouillons).toBeUndefined();
});

test('« Brouillons » demande les messages écrits jamais partis', async () => {
  const params = await paramsApres(() => cliquer('prospects-brouillons'));
  expect(params.brouillons).toBe('1');
  expect(params.tri).toBe('modif_recent');
  expect(params.envoyes).toBeUndefined();
});

test('les deux vues sont exclusives : la seconde remplace la première', async () => {
  const params = await paramsApres(async () => {
    await cliquer('prospects-derniers-envois');
    await cliquer('prospects-brouillons');
  });
  expect(params.brouillons).toBe('1');
  expect(params.envoyes).toBeUndefined();
});

test('un second clic désactive la vue et rend la liste entière', async () => {
  const params = await paramsApres(async () => {
    await cliquer('prospects-derniers-envois');
    await cliquer('prospects-derniers-envois');
  });
  expect(params.envoyes).toBeUndefined();
  expect(params.tri).toBeUndefined();
});

test('le tri « Plus anciens » part au serveur', async () => {
  const params = await paramsApres(() => changer('prospects-tri', 'ancien'));
  expect(params.tri).toBe('ancien');
});

test('la période part en INSTANTS absolus, calculés en heure de Neuchâtel', async () => {
  const params = await paramsApres(() => changer('prospects-periode', 'aujourdhui'));
  expect(params.depuis_iso).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
  expect(params.jusqu_a_iso).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
  // Exactement 24 h entre les deux bornes (hors jour de changement d'heure).
  const h = (Date.parse(params.jusqu_a_iso) - Date.parse(params.depuis_iso)) / 3600000;
  expect([23, 24, 25]).toContain(h);
});

test('« 30 derniers jours » couvre bien un mois', async () => {
  const params = await paramsApres(() => changer('prospects-periode', '30j'));
  const jours = (Date.parse(params.jusqu_a_iso) - Date.parse(params.depuis_iso)) / 86400000;
  expect(jours).toBeGreaterThan(29.9);
  expect(jours).toBeLessThan(30.2);
});

test('la période personnalisée ouvre deux champs de date et les envoie', async () => {
  const params = await paramsApres(async () => {
    await changer('prospects-periode', 'perso');
    await changer('prospects-debut', '2026-11-01');
    await changer('prospects-fin', '2026-11-10');
  });
  expect(par('prospects-debut')).not.toBeNull();
  expect(params.depuis_iso).toBe('2026-10-31T23:00:00.000Z');
  expect(params.jusqu_a_iso).toBe('2026-11-10T23:00:00.000Z');
});

test('période et filtres existants se combinent dans la MÊME requête', async () => {
  const params = await paramsApres(async () => {
    await changer('filtre-status', 'contacte');
    await changer('prospects-periode', '7j');
    await cliquer('prospects-derniers-envois');
  });
  expect(params.status).toBe('contacte');
  expect(params.envoyes).toBe('1');
  expect(params.depuis_iso).toBeTruthy();
});

test('« Tout afficher » remet les commandes à zéro', async () => {
  const params = await paramsApres(async () => {
    await cliquer('prospects-derniers-envois');
    await changer('prospects-periode', '7j');
    await cliquer('prospects-chrono-reset');
  });
  expect(Object.keys(params).sort()).toEqual(['limit', 'offset']);
});

test('aucun envoi : l’écran dit « aucun envoi », pas « aucun prospect »', async () => {
  mockEtatPilote = { etat: SECTION.OK, donnees: reponse([], 0) };
  await monter();
  await cliquer('prospects-derniers-envois');
  expect(par('prospects-vide').textContent).toContain('Aucun envoi enregistré pour cette sélection');
  expect(texte()).not.toContain('Aucun prospect pour le moment');
});

test('aucun brouillon : message propre à cette vue', async () => {
  mockEtatPilote = { etat: SECTION.OK, donnees: reponse([], 0) };
  await monter();
  await cliquer('prospects-brouillons');
  expect(par('prospects-vide').textContent).toContain('Aucun brouillon pour cette sélection');
});

test('consulter et filtrer n’écrit JAMAIS', async () => {
  mockEtatPilote = { etat: SECTION.OK, donnees: reponse([prospect()], 471) };
  await monter();
  await cliquer('prospects-derniers-envois');
  await changer('prospects-periode', '7j');
  await changer('prospects-tri', 'envoi_ancien');
  expect(axios.post).not.toHaveBeenCalled();
  expect(axios.patch).not.toHaveBeenCalled();
  expect(axios.put).not.toHaveBeenCalled();
  expect(axios.delete).not.toHaveBeenCalled();
});

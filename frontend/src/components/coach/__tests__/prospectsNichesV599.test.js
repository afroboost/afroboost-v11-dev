// V599 — les prospects référencent une niche de prospection_niches par son id stable.
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import ProspectsSection from '../ProspectsSection';
import ProspectionApercu from '../prospection/ProspectionApercu';
import { invaliderNiches } from '../../../hooks/useNichesProspection';
import { cleNicheProspect } from '../../../utils/prospectionStats';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), patch: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));

const SECTION = {
  ATTENTE: 'attente', CHARGEMENT: 'chargement', OK: 'ok',
  ERREUR: 'erreur', SESSION: 'session',
};

// Le pilote : il retient la source declaree par l'ecran et rend l'etat qu'on
// lui demande. `mockDerniereSource` permet de rejouer l'appel reel.
// (Le prefixe `mock` est impose par le hoisting de `jest.mock`.)
let mockEtatPilote = { etat: SECTION.OK, donnees: null, motif: 'serveur' };
let mockDerniereSource = null;
let mockSourcesDeclarees = null;
let mockEtatParSection = null;
const mockReessayer = jest.fn();

jest.mock('../../../hooks/useChargement', () => ({
  __esModule: true,
  SECTION: {
    ATTENTE: 'attente', CHARGEMENT: 'chargement', OK: 'ok',
    ERREUR: 'erreur', SESSION: 'session',
  },
  default: (sources) => {
    mockDerniereSource = sources.prospects;
    mockSourcesDeclarees = sources;
    const sections = {};
    Object.keys(sources).forEach((cle) => {
      const e = (mockEtatParSection && mockEtatParSection[cle]) || mockEtatPilote;
      sections[cle] = { etat: e.etat, donnees: e.donnees, motif: e.motif };
    });
    return {
      sections,
      reessayer: mockReessayer,
      global: mockEtatPilote.etat,
      donnees: {},
      cles: Object.keys(sources),
      chargement: mockEtatPilote.etat === 'chargement',
      sessionExpiree: mockEtatPilote.etat === 'session',
    };
  },
}));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

let conteneur = null;
let racine = null;

async function monter(element) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(element); });
  return conteneur;
}

afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) document.body.removeChild(conteneur);
  racine = null;
  conteneur = null;
  jest.clearAllMocks();
  mockDerniereSource = null;
  mockSourcesDeclarees = null;
  mockEtatParSection = null;
  mockEtatPilote = { etat: SECTION.OK, donnees: null, motif: 'serveur' };
});

const prospect = (sur) => Object.assign({
  id: 'p-1', ref: 'FES-01', organisation_name: "Festi'neuch", category: 'festival',
  city: 'Neuchâtel', address: 'Jeunes-Rives', website: 'festineuch.ch',
  instagram: '@festineuch', facebook: '', linkedin: '', tiktok: '',
  public_email: null, public_phone: null, contact_name: 'Resp. partenariats',
  contact_role: '', preferred_channel: 'Formulaire / DM', approach: '',
  score: 6.5, priority: 'B', wave: null, status: 'a_contacter',
  collaboration_type: null, notes: 'Idée de collaboration : Silent + QR',
  source_url: 'https://festineuch.ch', secondary_source_url: null,
  verified_at: null, j0_message: '', j3_message: '', j7_message: '',
  interested_message: '', first_contact_at: null, last_contact_at: null,
  next_followup_at: null, replied_at: null,
  partner_application_id: null, partner_id: null,
}, sur || {});

const reponse = (prospects, counts, total) => ({
  total: total === undefined ? prospects.length : total,
  returned: prospects.length,
  limit: 25,
  offset: 0,
  counts: Object.assign({
    a_contacter: 0, contacte: 0, repondu: 0, interesse: 0,
    sans_reponse_pause: 0, refuse: 0, total: prospects.length,
    candidature: 0, accepte: 0,
  }, counts || {}),
  prospects,
});


const par = (id) => document.querySelector(`[data-testid="${id}"]`);
const attendre = async () => { for (let i = 0; i < 8; i += 1) await act(async () => { await Promise.resolve(); }); };
const choisir = async (el, v) => {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
  await act(async () => { setter.call(el, v); el.dispatchEvent(new Event('change', { bubbles: true })); });
};
const saisir = async (el, v) => {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  await act(async () => { setter.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); });
};
const N = (cle, nom, ordre, sur) => Object.assign({ id: `0000000${ordre}-0000-4000-8000-00000000000${ordre}`, cle, nom, ordre, active: true, origine: ordre <= 6 }, sur || {});
const NICHES = [N('A', 'Partenaires locaux', 1), N('B', 'Étudiants / associations', 2), N('C', 'Festivals', 3), N('D', 'Écoles de danse', 4),
  N('E', 'Entreprises', 5), N('F', 'Santé / mamans', 6)];
const SENIORS = N('x', 'TEST — Seniors', 7); SENIORS.cle = SENIORS.id;
const ARCHIVEE = N('y', 'Ancienne', 8, { active: false }); ARCHIVEE.cle = ARCHIVEE.id;

beforeEach(() => {
  invaliderNiches();
  axios.get.mockImplementation((url) => Promise.resolve(url.endsWith('/prospection-niches')
    ? { data: { niches: [...NICHES, SENIORS, ARCHIVEE] } } : { data: {} }));
});

test('cleNicheProspect : lit niche_id ; sinon la règle historique ; id inconnu = non classé', () => {
  const cle = cleNicheProspect([...NICHES, SENIORS]);
  expect(cle({ niche_id: NICHES[2].id, category: 'bar' })).toBe('C');
  expect(cle({ niche_id: SENIORS.id })).toBe(SENIORS.cle);
  expect(cle({ category: 'ecole_danse' })).toBe('D');               // pas encore rattaché
  expect(cle({ niche_id: 'inconnu', category: 'bar' })).toBe('');
});

const fiche = (sur) => Object.assign({ id: 'p-1', ref: 'TST-01', organisation_name: 'TEST — Résidence', category: 'association',
  city: 'Neuchâtel', status: 'repondu', priority: '', wave: null, niche_id: SENIORS.id }, sur || {});
const rep = (prospects) => ({ total: prospects.length, returned: prospects.length, limit: 25, offset: 0,
  counts: { total: prospects.length }, prospects });

test('filtre « Niche » : toutes les niches du serveur (G comprise), « Sans niche » ; envoyé au serveur par id', async () => {
  mockEtatPilote = { etat: SECTION.OK, donnees: rep([fiche()]) };
  await monter(<ProspectsSection API="/api" />);
  await attendre();
  const options = [...par('filtre-niche').options].map((o) => o.textContent);
  expect(options).toEqual(['Toutes les niches', 'A — Partenaires locaux', 'B — Étudiants / associations', 'C — Festivals',
    'D — Écoles de danse', 'E — Entreprises', 'F — Santé / mamans', 'G — TEST — Seniors', 'H — Ancienne (archivée)', 'Sans niche']);
  await choisir(par('filtre-niche'), SENIORS.id);
  axios.get.mockResolvedValue({ data: rep([]) });
  await act(async () => { await mockDerniereSource.appel(); });
  const appel = axios.get.mock.calls.filter(([u]) => u === '/api/partner-prospects').pop();
  expect(appel[1].params.niche_id).toBe(SENIORS.id);
});

test('fiche : le champ Niche ne propose que les actives (+ celle déjà portée) ; changer n’envoie QUE niche_id', async () => {
  axios.patch.mockResolvedValue({ data: fiche({ niche_id: NICHES[3].id }) });
  mockEtatPilote = { etat: SECTION.OK, donnees: rep([fiche({ niche_id: ARCHIVEE.id })]) };
  await monter(<ProspectsSection API="/api" />);
  await attendre();
  await act(async () => { par('ligne-TST-01').click(); });
  const options = [...par('edit-niche').options].map((o) => o.textContent);
  expect(options).toContain('H — Ancienne (archivée)');                   // déjà portée : conservée
  expect(options).toContain('G — TEST — Seniors');
  expect(par('edit-niche').value).toBe(ARCHIVEE.id);
  expect(par('fiche-entete-etat').textContent).toMatch(/H — Ancienne \(archivée\)/);
  await choisir(par('edit-niche'), NICHES[3].id);
  const bouton = [...document.querySelectorAll('button')].find((b) => /^Enregistrer/.test((b.textContent || '').trim()));
  await act(async () => { bouton.click(); });
  await attendre();
  expect(axios.patch).toHaveBeenCalledTimes(1);
  expect(axios.patch).toHaveBeenCalledWith('/api/partner-prospects/p-1', { niche_id: NICHES[3].id });
});

test('fiche d’une AUTRE niche : l’archivée n’est pas proposée', async () => {
  mockEtatPilote = { etat: SECTION.OK, donnees: rep([fiche({ niche_id: NICHES[2].id })]) };
  await monter(<ProspectsSection API="/api" />);
  await attendre();
  await act(async () => { par('ligne-TST-01').click(); });
  expect([...par('edit-niche').options].map((o) => o.textContent)).not.toContain('H — Ancienne (archivée)');
});

test('+ Ajouter un prospect : petite fenêtre, crée SEULEMENT la fiche (nom, catégorie, ville, niche active)', async () => {
  axios.post.mockResolvedValue({ data: { id: 'n' } });
  mockEtatPilote = { etat: SECTION.OK, donnees: rep([]) };
  await monter(<ProspectsSection API="/api" />);
  await attendre();
  await act(async () => { par('prospect-ajouter').click(); });
  expect([...par('creation-niche').options].map((o) => o.textContent)).not.toContain('H — Ancienne (archivée)');
  await saisir(par('creation-nom'), 'TEST — Résidence Exemple');
  await choisir(par('creation-categorie'), 'association');
  await choisir(par('creation-niche'), SENIORS.id);
  await act(async () => { par('prospect-creation').querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });
  await attendre();
  expect(axios.post).toHaveBeenCalledTimes(1);
  expect(axios.post).toHaveBeenCalledWith('/api/partner-prospects',
    { organisation_name: 'TEST — Résidence Exemple', category: 'association', niche_id: SENIORS.id });
  expect(par('prospect-creation')).toBeNull();
});

test('doublon possible (409) : montré, « Créer quand même » renvoie avec allow_duplicate', async () => {
  axios.post.mockRejectedValueOnce({ response: { status: 409, data: { detail: { possible_duplicates: [{ organisation_name: 'Résidence Exemple' }] } } } })
    .mockResolvedValueOnce({ data: { id: 'n' } });
  mockEtatPilote = { etat: SECTION.OK, donnees: rep([]) };
  await monter(<ProspectsSection API="/api" />);
  await attendre();
  await act(async () => { par('prospect-ajouter').click(); });
  await saisir(par('creation-nom'), 'Résidence Exemple');
  await choisir(par('creation-categorie'), 'association');
  await act(async () => { par('prospect-creation').querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });
  await attendre();
  expect(par('creation-doublons').textContent).toMatch(/Résidence Exemple/);
  await act(async () => { par('creation-forcer').click(); });
  await attendre();
  expect(axios.post.mock.calls[1][1]).toEqual({ organisation_name: 'Résidence Exemple', category: 'association', allow_duplicate: true });
});

test('Vue d’ensemble compte par niche_id : nouvelle niche à 3 → 3 ; nouvelle niche vide → affichée à 0', async () => {
  const VIDE = N('z', 'TEST — Vide', 9); VIDE.cle = VIDE.id;
  const fiches = [
    fiche({ id: 'a', niche_id: SENIORS.id }), fiche({ id: 'b', niche_id: SENIORS.id }), fiche({ id: 'c', niche_id: SENIORS.id }),
    fiche({ id: 'd', niche_id: NICHES[2].id, category: 'festival' }),
  ];
  axios.get.mockImplementation((url) => Promise.resolve(
    url.endsWith('/prospection-niches') ? { data: { niches: [...NICHES, SENIORS, VIDE] } }
      : url.endsWith('/partner-prospects') ? { data: { total: fiches.length, prospects: fiches } }
        : url.endsWith('/calendar-events') ? { data: { events: [] } } : { data: {} }));
  await monter(<ProspectionApercu API="/api-v599" />);
  await attendre();
  const lignes = [...document.querySelectorAll('[data-testid="pp-niches-ligne"]')].map((tr) => [...tr.children].slice(0, 2).map((td) => td.textContent).join(' = '));
  expect(lignes).toContain('G — TEST — Seniors = 3');
  expect(lignes).toContain('C — Festivals = 1');
  expect(lignes).toContain('I — TEST — Vide = 0');
});

test('V600 — niche dans la Corbeille : la fiche affiche « Niche supprimée », plus aucun choix ne la propose', async () => {
  const SUPPR = { ...SENIORS, supprimee: true };
  axios.get.mockImplementation((url) => Promise.resolve(url.endsWith('/prospection-niches')
    ? { data: { niches: [...NICHES, SUPPR] } } : { data: {} }));
  mockEtatPilote = { etat: SECTION.OK, donnees: rep([fiche({ niche_id: SUPPR.id })]) };
  await monter(<ProspectsSection API="/api" />);
  await attendre();
  expect([...par('filtre-niche').options].map((o) => o.textContent).join('|')).not.toMatch(/Seniors/);
  await act(async () => { par('ligne-TST-01').click(); });
  expect(par('fiche-entete-etat').textContent).toMatch(/Niche supprimée — TEST — Seniors/);
  expect([...par('edit-niche').options].map((o) => o.textContent)).toContain('Niche supprimée — TEST — Seniors');
  await act(async () => { par('fermer-fiche').click(); });
  await act(async () => { par('prospect-ajouter').click(); });
  expect([...par('creation-niche').options].map((o) => o.textContent).join('|')).not.toMatch(/Seniors/);
});

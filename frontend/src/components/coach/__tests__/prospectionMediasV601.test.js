// V601 — une niche peut porter plusieurs vidéos (une par public visé) : chaque public a ses
// emplacements, aucune vidéo n'en masque une autre, et « Ajouter » dans un public envoie ce public.
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import ProspectionMedias, { statutPublics } from '../prospection/ProspectionMedias';
import { invaliderNiches } from '../../../hooks/useNichesProspection';

jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn(), delete: jest.fn() } }));
jest.mock('../prospection/ProspectionVideoEditeur', () => ({ __esModule: true, default: () => <div /> }));
global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const NICHES = [['A', 'Partenaires locaux'], ['E', 'Entreprises']].map(([cle, nom], i) => ({ id: `id-${cle}`, cle, nom, ordre: i === 0 ? 1 : 5, active: true, origine: true }));
const COIF = { id: 'salons-coiffure-beaute', nom: 'Salons / coiffure / beauté', mots_cles: ['coiffure'] };
const PHYS = { id: 'physio-osteo-therapie', nom: 'Physio / ostéo / thérapie', mots_cles: ['physio'] };
const MEDIAS = [
  { id: 'c', niche: 'A', format: 'original', statut: 'en_cours', url: 'https://x/c.mp4', cible: COIF, cible_id: COIF.id, fichier: { nom: 'c.mp4' } },
  { id: 'p', niche: 'A', format: 'original', statut: 'en_cours', url: 'https://x/p.mp4', cible: PHYS, cible_id: PHYS.id, fichier: { nom: 'p.mp4' } },
];

let conteneur; let racine;
beforeEach(() => {
  invaliderNiches();
  ['get', 'post', 'patch', 'delete'].forEach((m) => axios[m].mockReset());
  axios.get.mockImplementation((url) => Promise.resolve(url.endsWith('/prospection-niches') ? { data: { niches: NICHES } } : { data: { medias: MEDIAS } }));
  conteneur = document.createElement('div'); document.body.appendChild(conteneur); racine = createRoot(conteneur);
});
afterEach(() => { act(() => racine.unmount()); conteneur.remove(); });
const attendre = async () => { for (let i = 0; i < 8; i += 1) await act(async () => { await Promise.resolve(); }); };
const q = (id) => document.querySelector(`[data-testid="${id}"]`);

test('la niche A montre ses DEUX vidéos, chacune sous son public', async () => {
  await act(async () => { racine.render(<ProspectionMedias API="/api" />); }); await attendre();
  expect(q('pm-resume-A').textContent).toBe('2 médias');
  await act(async () => { q('pm-niche-ligne-A').click(); }); await attendre();
  expect(q(`pm-public-nom-A-${COIF.id}`).textContent).toBe('Public : Salons / coiffure / beauté');
  expect(q(`pm-public-nom-A-${PHYS.id}`).textContent).toBe('Public : Physio / ostéo / thérapie');
  expect(q('pm-public-A-general')).toBeNull();
  expect(q(`pm-public-A-${COIF.id}`).textContent).toMatch(/c\.mp4|Original/);
});

test('une niche sans vidéo garde ses emplacements vides, sans titre de public', async () => {
  await act(async () => { racine.render(<ProspectionMedias API="/api" />); }); await attendre();
  expect(q('pm-resume-E').textContent).toBe('Aucun média');
  await act(async () => { q('pm-niche-ligne-E').click(); }); await attendre();
  expect(q('pm-public-E-general')).not.toBeNull();
  expect(q('pm-public-nom-E-general')).toBeNull();
});

test('statut d’une niche à plusieurs publics : validée seulement si tous le sont', () => {
  const v = { actuels: { '16_9': { statut: 'validee' } } };
  const e = { actuels: { original: { statut: 'en_cours' } } };
  const a = { actuels: { '16_9': { statut: 'a_verifier' } } };
  expect(statutPublics([v, v])).toBe('validee');
  expect(statutPublics([v, e])).toBe('en_cours');
  expect(statutPublics([v, a])).toBe('a_verifier');
});

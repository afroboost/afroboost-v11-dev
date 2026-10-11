// V598 — niches gérables : la liste vient du serveur (/prospection-niches), une niche créée
// apparaît comme les autres (5 emplacements, aucun fichier), renommer / archiver / supprimer
// passent par une confirmation, et seule une niche CRÉÉE et VIDE propose « Supprimer ».
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import ProspectionMedias from '../prospection/ProspectionMedias';
import { invaliderNiches } from '../../../hooks/useNichesProspection';
import { lettreNiche, libellesNiches } from '../../../utils/prospectionStats';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), patch: jest.fn(), delete: jest.fn() },
}));
jest.mock('../prospection/ProspectionVideoEditeur', () => ({ __esModule: true, default: () => <div data-testid="editeur-temoin" /> }));
global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const ORIGINE = [['A', 'Partenaires locaux'], ['B', 'Étudiants / associations'], ['C', 'Festivals'], ['D', 'Écoles de danse'], ['E', 'Entreprises'], ['F', 'Santé / mamans']]
  .map(([cle, nom], i) => ({ id: `id-${cle}`, cle, nom, ordre: i + 1, active: true, origine: true }));
const SENIORS = { id: '11111111-1111-4111-8111-111111111111', cle: '11111111-1111-4111-8111-111111111111', nom: 'TEST — Seniors', ordre: 7, active: true, origine: false };
const ARCHIVEE = { id: '22222222-2222-4222-8222-222222222222', cle: '22222222-2222-4222-8222-222222222222', nom: 'Vieille niche', ordre: 8, active: false, origine: false };
const MEDIAS = [{ id: 'orig', niche: 'C', format: 'original', statut: 'en_cours', url: '/api/files/o1/video_o1.mp4', fichier: { duree: 49 } }];
let NICHES_SRV;

let conteneur; let racine;
beforeEach(() => {
  invaliderNiches();
  NICHES_SRV = [...ORIGINE, SENIORS, ARCHIVEE];
  ['get', 'post', 'patch', 'delete'].forEach((m) => axios[m].mockReset());
  axios.get.mockImplementation((url) => Promise.resolve(url.endsWith('/prospection-niches')
    ? { data: { niches: NICHES_SRV } }
    : { data: { total: MEDIAS.length, medias: MEDIAS } }));
  axios.post.mockImplementation(() => Promise.resolve({ data: { niche: {} } }));
  axios.patch.mockImplementation(() => Promise.resolve({ data: { niche: {} } }));
  axios.delete.mockImplementation(() => Promise.resolve({ data: { supprime: true } }));
  conteneur = document.createElement('div'); document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
});
afterEach(() => { act(() => racine.unmount()); conteneur.remove(); document.body.innerHTML = ''; });

const attendre = async () => { for (let i = 0; i < 8; i += 1) await act(async () => { await Promise.resolve(); }); };
async function monter() { await act(async () => { racine.render(<ProspectionMedias API="/api" />); }); await attendre(); }
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
const clic = async (el) => { await act(async () => { el.click(); }); await attendre(); };
const saisir = async (el, v) => {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  await act(async () => { setter.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); });
};
const soumettre = async () => { await act(async () => { q('pm-fenetre-niche').querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); }); await attendre(); };

test('lettres calculées depuis l’ordre, libellés depuis le serveur', () => {
  expect([1, 6, 7, 26, 27].map(lettreNiche)).toEqual(['A', 'F', 'G', 'Z', 'AA']);
  expect(libellesNiches([SENIORS])[SENIORS.cle]).toBe('G — TEST — Seniors');
});

test('la niche créée apparaît comme les autres (G, fermée, 5 emplacements vides) ; l’archivée est rangée à part', async () => {
  await monter();
  expect(document.querySelectorAll('[data-testid^="pm-niche-ligne-"]').length).toBe(7);
  expect(q('pm-nom-G').textContent).toBe('G — TEST — Seniors');
  expect(q('pm-resume-G').textContent).toBe('Aucun média');
  expect(q('pm-statut-niche-G').textContent).toBe('En cours');
  expect(q('pm-niche-ligne-H')).toBeNull();
  expect(q('pm-niches-archivees').textContent).toBe('Niches archivées (1)');
  await clic(q('pm-niche-ligne-G'));
  ['original', '16_9', '9_16', '1_1', 'miniature'].forEach((f) => expect(q(`pm-emplacement-${f}`).textContent).toMatch(/Ajouter/));
  expect(axios.post).not.toHaveBeenCalled();
});

test('+ Ajouter une niche : petite fenêtre, « Créer » envoie UNIQUEMENT le nom', async () => {
  await monter();
  await clic(q('pm-niche-ajouter'));
  expect(q('pm-fenetre-niche').textContent).toMatch(/Ajouter une niche/);
  expect(q('pm-niche-annuler').textContent).toBe('Annuler');
  expect(q('pm-niche-ok').textContent).toBe('Créer');
  await saisir(q('pm-niche-nom'), 'Personnes âgées / seniors');
  NICHES_SRV = [...NICHES_SRV, { ...SENIORS, id: 'x', cle: 'x', nom: 'Personnes âgées / seniors', ordre: 9 }];
  await soumettre();
  expect(axios.post).toHaveBeenCalledTimes(1);
  expect(axios.post).toHaveBeenCalledWith('/api/prospection-niches', { nom: 'Personnes âgées / seniors' });
  expect(q('pm-fenetre-niche')).toBeNull();
  expect(q('pm-info').textContent).toMatch(/aucun prospect, message ni lien/);
});

test('Annuler la fenêtre ne crée rien', async () => {
  await monter();
  await clic(q('pm-niche-ajouter'));
  await clic(q('pm-niche-annuler'));
  expect(q('pm-fenetre-niche')).toBeNull();
  expect(axios.post).not.toHaveBeenCalled();
});

test('Renommer : PATCH du seul nom, sur l’id stable', async () => {
  await monter();
  await clic(q('pm-niche-menu-G'));
  await clic(q('pm-niche-renommer-G'));
  expect(q('pm-niche-nom').value).toBe('TEST — Seniors');
  await saisir(q('pm-niche-nom'), 'TEST — Seniors / 60+');
  await soumettre();
  expect(axios.patch).toHaveBeenCalledWith(`/api/prospection-niches/${SENIORS.id}`, { nom: 'TEST — Seniors / 60+' });
});

test('Archiver : confirmation, puis active=false ; Réactiver depuis la liste des archivées', async () => {
  await monter();
  await clic(q('pm-niche-menu-G'));
  await clic(q('pm-niche-archiver-G'));
  expect(q('pm-confirmation').textContent).toMatch(/Archiver cette niche \?/);
  expect(q('pm-confirmation').textContent).toMatch(/conservés/);
  expect(axios.patch).not.toHaveBeenCalled();
  await clic(q('pm-confirmation-ok'));
  expect(axios.patch).toHaveBeenCalledWith(`/api/prospection-niches/${SENIORS.id}`, { active: false });
  axios.patch.mockClear();
  await clic(q('pm-niches-archivees'));
  await clic(q('pm-niche-reactiver-H'));
  await clic(q('pm-confirmation-ok'));
  expect(axios.patch).toHaveBeenCalledWith(`/api/prospection-niches/${ARCHIVEE.id}`, { active: true });
});

test('V600 — Supprimer : proposé pour TOUTE niche ; confirmation avec les vrais comptes ; Annuler ne supprime rien', async () => {
  axios.get.mockImplementation((url) => Promise.resolve(url.endsWith('/prospection-niches')
    ? { data: { niches: NICHES_SRV } }
    : url.endsWith('/contenu') ? { data: { contenu: { prospects: 95, medias: 3, liens: 1 } } }
      : { data: { total: MEDIAS.length, medias: MEDIAS } }));
  await monter();
  await clic(q('pm-niche-menu-C'));                   // d'origine, avec un média : supprimable (Corbeille)
  await clic(q('pm-niche-supprimer-C'));
  const conf = q('pm-confirmation').textContent;
  expect(conf).toMatch(/Supprimer « Festivals » \?/);
  expect(conf).toMatch(/95 prospects, 3 médias, 1 lien/);
  expect(conf).toMatch(/ne seront pas supprimés/);
  expect(q('pm-confirmation-ok').textContent).toBe('Supprimer la niche');
  await clic(q('pm-confirmation-annuler'));
  expect(axios.delete).not.toHaveBeenCalled();
  await clic(q('pm-niche-menu-G'));
  await clic(q('pm-niche-supprimer-G'));
  await clic(q('pm-confirmation-ok'));
  expect(axios.delete).toHaveBeenCalledTimes(1);
  expect(axios.delete).toHaveBeenCalledWith(`/api/prospection-niches/${SENIORS.id}`);
});

test('V600 — une niche dans la Corbeille n’apparaît ni dans les actives, ni dans les archivées', async () => {
  NICHES_SRV = [...ORIGINE, { ...SENIORS, supprimee: true }, ARCHIVEE];
  await monter();
  expect(q('pm-niche-ligne-G')).toBeNull();
  expect(document.querySelectorAll('[data-testid^="pm-niche-ligne-"]').length).toBe(6);
  expect(q('pm-niches-archivees').textContent).toBe('Niches archivées (1)');
});

test('serveur muet : les six niches d’origine restent affichées (repli)', async () => {
  axios.get.mockImplementation((url) => (url.endsWith('/prospection-niches')
    ? Promise.reject(new Error('réseau'))
    : Promise.resolve({ data: { medias: [] } })));
  await monter();
  expect(document.querySelectorAll('[data-testid^="pm-niche-ligne-"]').length).toBe(6);
  expect(q('pm-nom-C').textContent).toBe('C — Festivals');
});

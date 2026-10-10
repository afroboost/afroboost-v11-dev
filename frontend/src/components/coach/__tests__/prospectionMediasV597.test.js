// V597 — Prospection → Médias : design épuré (accordéon, emplacements compacts, éditeur en
// fenêtre) + « Supprimer » via la Corbeille, TOUJOURS après confirmation.
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import ProspectionMedias, { statutNiche } from '../prospection/ProspectionMedias';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), patch: jest.fn(), delete: jest.fn() },
}));
// L'éditeur (et son moteur) est chargé à la demande : ici, un simple témoin.
jest.mock('../prospection/ProspectionVideoEditeur', () => ({
  __esModule: true,
  default: (p) => <div data-testid="editeur-temoin">{p.original.id}|{String(p.ratioInitial)}</div>,
}));
global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const MEDIAS = [
  { id: 'orig', niche: 'C', format: 'original', statut: 'en_cours', url: '/api/files/o1/video_o1.mp4', fichier: { nom: 'AFROBOOST_6_FESTIVAL_16x9_AVEC-COACH.mp4', duree: 49.1, largeur: 1920, hauteur: 1080, taille: 16409997 }, created_at: '2026-10-10T17:00:00+00:00' },
  { id: 'x916', niche: 'C', format: '9_16', statut: 'a_verifier', url: '/api/files/e1/video_e1.mp4', source_id: 'orig', edition: { debut: 2, fin: 40, ratio: '9:16', position: 0.05 }, fichier: { nom: 'f_9x16.mp4', duree: 38.1, largeur: 608, hauteur: 1080 }, created_at: '2026-10-10T17:10:00+00:00' },
  { id: 'x169', niche: 'C', format: '16_9', statut: 'a_verifier', url: '/api/files/e2/video_e2.mp4', source_id: 'orig', edition: { debut: 2, fin: 40, ratio: '16:9', position: 0.5 }, fichier: { nom: 'f_16x9.mp4', duree: 38.1, largeur: 1920, hauteur: 1080 }, created_at: '2026-10-10T17:20:00+00:00' },
  { id: 'mini', niche: 'C', format: 'miniature', statut: 'en_cours', url: '/api/files/m1/image_m1.jpg', source_id: 'orig', fichier: { nom: 'm.jpg' }, created_at: '2026-10-10T17:05:00+00:00' },
];

let conteneur; let racine;
beforeEach(() => {
  ['get', 'post', 'patch', 'delete'].forEach((m) => axios[m].mockReset());
  axios.get.mockImplementation(() => Promise.resolve({ data: { total: MEDIAS.length, medias: MEDIAS, defaut_par_niche: {} } }));
  axios.delete.mockImplementation(() => Promise.resolve({ data: { supprime: true } }));
  conteneur = document.createElement('div'); document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
});
afterEach(() => { act(() => racine.unmount()); conteneur.remove(); document.body.innerHTML = ''; });

async function monter() {
  await act(async () => { racine.render(<ProspectionMedias API="/api" />); });
  for (let i = 0; i < 8; i += 1) await act(async () => { await Promise.resolve(); });
}
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
const clic = async (el) => { await act(async () => { el.click(); }); for (let i = 0; i < 6; i += 1) await act(async () => { await Promise.resolve(); }); };

test('au chargement : 6 lignes compactes, toutes FERMÉES, aucun lecteur ni éditeur', async () => {
  await monter();
  expect(document.querySelectorAll('[data-testid^="pm-niche-ligne-"]').length).toBe(6);
  ['A', 'B', 'C', 'D', 'E', 'F'].forEach((n) => {
    expect(q(`pm-niche-ligne-${n}`).getAttribute('aria-expanded')).toBe('false');
    expect(q(`pm-contenu-${n}`)).toBeNull();
  });
  expect(document.querySelectorAll('video').length).toBe(0);
  expect(q('pm-fenetre-editeur')).toBeNull();
  expect(q('pm-resume-C').textContent).toBe('4 médias · 2 à vérifier');
  expect(q('pm-statut-niche-C').textContent).toBe('À vérifier');
  expect(q('pm-statut-niche-A').textContent).toBe('En cours');
  expect(q('pm-resume-A').textContent).toBe('Aucun média');
  expect(axios.post).not.toHaveBeenCalled();
});

test('une seule niche ouverte à la fois', async () => {
  await monter();
  await clic(q('pm-niche-ligne-C'));
  expect(q('pm-contenu-C')).toBeTruthy();
  await clic(q('pm-niche-ligne-E'));
  expect(q('pm-contenu-C')).toBeNull();
  expect(q('pm-contenu-E')).toBeTruthy();
  await clic(q('pm-niche-ligne-E'));
  expect(q('pm-contenu-E')).toBeNull();
});

test('niche ouverte : emplacement vide = « + Ajouter », rempli = 1 action + ⋯, pas de détails techniques visibles', async () => {
  await monter();
  await clic(q('pm-niche-ligne-C'));
  const vide = q('pm-emplacement-1_1');
  expect(vide.textContent).toMatch(/1:1/);
  expect(vide.textContent).toMatch(/Ajouter/);
  const plein = q('pm-emplacement-9_16');
  expect(plein.textContent).toMatch(/9:16 · 00:38/);
  expect(plein.textContent).toMatch(/À vérifier/);
  expect(plein.querySelectorAll('button').length).toBe(2);            // Remodifier + ⋯
  expect(q('pm-contenu-C').textContent).not.toMatch(/608 × 1080|f_9x16\.mp4|\d+(\.\d+)? Mo/);
  await clic(q('pm-menu-9_16'));
  await clic(q('pm-menu-details-9_16'));
  expect(q('pm-details-9_16').textContent).toMatch(/608 × 1080/);
});

test('Supprimer : confirmation obligatoire ; Annuler ne supprime rien', async () => {
  await monter();
  await clic(q('pm-niche-ligne-C'));
  await clic(q('pm-menu-9_16'));
  await clic(q('pm-menu-supprimer-9_16'));
  expect(q('pm-confirmation').textContent).toMatch(/Supprimer ce média \?/);
  expect(q('pm-confirmation-annuler').textContent).toBe('Annuler');
  expect(q('pm-confirmation-ok').textContent).toBe('Supprimer');
  await clic(q('pm-confirmation-annuler'));
  expect(q('pm-confirmation')).toBeNull();
  expect(axios.delete).not.toHaveBeenCalled();
});

test('Supprimer confirmé : UNE requête, sur le seul média choisi', async () => {
  await monter();
  await clic(q('pm-niche-ligne-C'));
  for (const [fmt, id] of [['9_16', 'x916'], ['miniature', 'mini'], ['original', 'orig']]) {
    axios.delete.mockClear();
    await clic(q(`pm-menu-${fmt}`));
    await clic(q(`pm-menu-supprimer-${fmt}`));
    await clic(q('pm-confirmation-ok'));
    expect(axios.delete).toHaveBeenCalledTimes(1);
    expect(axios.delete).toHaveBeenCalledWith(`/api/prospection-medias/${id}`);
  }
  expect(axios.patch).not.toHaveBeenCalled();
});

test('Supprimer est proposé sur les 5 emplacements remplis (16:9, 1:1 inclus)', async () => {
  axios.get.mockImplementation(() => Promise.resolve({ data: { medias: [...MEDIAS, { id: 'x11', niche: 'C', format: '1_1', statut: 'a_verifier', url: '/api/files/e3/video_e3.mp4', source_id: 'orig' }] } }));
  await monter();
  await clic(q('pm-niche-ligne-C'));
  for (const fmt of ['original', '16_9', '9_16', '1_1', 'miniature']) {
    await clic(q(`pm-menu-${fmt}`));
    expect(q(`pm-menu-supprimer-${fmt}`)).toBeTruthy();
    await clic(q(`pm-menu-${fmt}`));
  }
});

test('Valider passe aussi par une confirmation', async () => {
  axios.patch.mockImplementation(() => Promise.resolve({ data: {} }));
  await monter();
  await clic(q('pm-niche-ligne-C'));
  await clic(q('pm-menu-16_9'));
  await clic(q('pm-menu-valider-16_9'));
  expect(q('pm-confirmation').textContent).toMatch(/Valider cette vidéo/);
  expect(axios.patch).not.toHaveBeenCalled();
  await clic(q('pm-confirmation-ok'));
  expect(axios.patch).toHaveBeenCalledWith('/api/prospection-medias/x169', { statut: 'validee' });
});

test('l’éditeur s’ouvre dans une FENÊTRE (hors de la page), sur l’original ; « + Ajouter » 1:1 présélectionne 1:1', async () => {
  await monter();
  await clic(q('pm-niche-ligne-C'));
  await clic(q('pm-editer-9_16'));
  for (let i = 0; i < 6; i += 1) await act(async () => { await Promise.resolve(); });
  const fenetre = q('pm-fenetre-editeur');
  expect(fenetre).toBeTruthy();
  expect(conteneur.contains(fenetre)).toBe(false);                   // portée sur <body>, pas dans la page
  expect(q('editeur-temoin').textContent).toBe('orig|null');
  await act(async () => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); });
  expect(q('pm-fenetre-editeur')).toBeNull();
  await clic(q('pm-ajouter-1_1'));
  for (let i = 0; i < 6; i += 1) await act(async () => { await Promise.resolve(); });
  expect(q('editeur-temoin').textContent).toBe('orig|1:1');
});

test('statutNiche : validée si le 16:9 l’est, à vérifier si un média attend, sinon en cours', () => {
  expect(statutNiche({})).toBe('en_cours');
  expect(statutNiche({ '9_16': { statut: 'a_verifier' } })).toBe('a_verifier');
  expect(statutNiche({ '16_9': { statut: 'validee' }, '9_16': { statut: 'a_verifier' } })).toBe('validee');
});

test('icônes SVG uniquement ; couleur de marque toujours via var(--primary-color)', () => {
  const fs = require('fs'); const path = require('path');
  const src = fs.readFileSync(path.join(__dirname, '..', 'prospection', 'ProspectionMedias.js'), 'utf8');
  expect(src).not.toMatch(/[\u{1F300}-\u{1FAFF}\u2600-\u27BF]/u);
  const marque = /#(D91CD2|a855f7|8B5CF6|9333ea)/gi;
  const hors = src.replace(/var\(--primary-color, #D91CD2\)/g, '').match(marque);
  expect(hors).toBeNull();
});

test('fenêtre et confirmation passent AU-DESSUS des boutons fixes du tableau de bord (z-index 9999)', async () => {
  await monter();
  await clic(q('pm-niche-ligne-C'));
  await clic(q('pm-editer-9_16'));
  expect(Number(q('pm-fenetre-editeur').style.zIndex)).toBeGreaterThan(9999);
  await act(async () => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); });
  await clic(q('pm-menu-9_16'));
  await clic(q('pm-menu-supprimer-9_16'));
  expect(Number(q('pm-confirmation').style.zIndex)).toBeGreaterThan(9999);
});

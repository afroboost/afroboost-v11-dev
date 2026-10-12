/**
 * V610k — « Mes invitations » : menu « ⋯ » -> Dupliquer / Supprimer (logique) ; Corbeille.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn(), create: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } }));
jest.mock('../EditeurInvitation', () => function E(p) { return <div data-testid="editeur-ouvert" data-id={p.invitationId} />; });
jest.mock('../InvitationModal', () => function M() { return null; });
// eslint-disable-next-line import/first
import axios from 'axios';
// eslint-disable-next-line import/first
import MesInvitations from '../MesInvitations';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let conteneur = null; let racine = null;
afterEach(() => { if (racine) act(() => racine.unmount()); if (conteneur) conteneur.remove(); racine = null; conteneur = null; jest.clearAllMocks(); });
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
async function attendre(fn) { let e; for (let i = 0; i < 40; i += 1) { try { fn(); return; } catch (x) { e = x; } await act(async () => { await new Promise((r) => setTimeout(r, 20)); }); } throw e; }
const INV = (id, status, type = 'event_paid') => ({ id, type, status, title: `Inv ${id}`, share_url: `https://afroboost.com/i/${id}`, card_url: '/c.jpg' });

async function monter(items, archivees = []) {
  axios.get.mockImplementation((url, opt) => {
    if (String(url).includes('/donnees-liees')) return Promise.resolve({ data: { a_des_donnees: url.includes('A1'), liens_personnels: url.includes('A1') ? 2 : 0 } });
    if (opt && opt.params && opt.params.include_archived) return Promise.resolve({ data: { items: items.concat(archivees) } });
    return Promise.resolve({ data: { items } });
  });
  conteneur = document.createElement('div'); document.body.appendChild(conteneur); racine = createRoot(conteneur);
  await act(async () => { racine.render(<MesInvitations API="/api" />); });
  await attendre(() => expect(q(`mes-inv-${items[0].id}`)).toBeTruthy());
}

test('menu : Dupliquer, Masquer (si active), Statistiques, Supprimer — plus d\'« Archiver »', async () => {
  await monter([INV('A1', 'active')]);
  await act(async () => { q('mes-inv-plus-A1').click(); });
  const items = [...document.querySelectorAll('[role=menuitem]')].map((e) => e.textContent.trim());
  expect(items).toEqual(['Voir la page', 'Dupliquer', 'Masquer', 'Statistiques', 'Supprimer']);
});

test('Dupliquer : POST /dupliquer puis ouvre la COPIE dans l\'éditeur', async () => {
  await monter([INV('D1', 'draft', 'trial')]);
  axios.post.mockResolvedValue({ data: INV('COPIE1', 'draft', 'trial') });
  await act(async () => { q('mes-inv-plus-D1').click(); });
  await act(async () => { q('mes-inv-dupliquer-D1').click(); });
  expect(axios.post).toHaveBeenCalledWith('/api/referral/campaigns/D1/dupliquer', {}, expect.anything());
  await attendre(() => expect(q('editeur-ouvert').getAttribute('data-id')).toBe('COPIE1'));
});

test('Supprimer : confirmation exacte ; avec données -> « archivée plutôt que supprimée » ; Annuler ne fait rien', async () => {
  await monter([INV('A1', 'active')]);
  await act(async () => { q('mes-inv-plus-A1').click(); });
  await act(async () => { q('mes-inv-supprimer-A1').click(); });
  const boite = q('mes-inv-supprimer-confirmation-A1');
  expect(boite.textContent).toContain('Supprimer cette invitation ?');
  expect(boite.textContent).toContain('Elle ne sera plus visible dans Mes invitations. Les données historiques nécessaires seront conservées.');
  await attendre(() => expect(q('mes-inv-supprimer-donnees-A1').textContent).toBe('Cette invitation contient des données. Elle sera archivée plutôt que supprimée définitivement.'));
  await act(async () => { q('mes-inv-supprimer-annuler-A1').click(); });
  expect(q('mes-inv-supprimer-confirmation-A1')).toBeNull();
  expect(axios.post).not.toHaveBeenCalled();
  await act(async () => { q('mes-inv-plus-A1').click(); });
  await act(async () => { q('mes-inv-supprimer-A1').click(); });
  await attendre(() => expect(q('mes-inv-supprimer-ok-A1').disabled).toBe(false));
  axios.post.mockResolvedValue({ data: { supprimee: true, definitive: false } });
  await act(async () => { q('mes-inv-supprimer-ok-A1').click(); });
  expect(axios.post).toHaveBeenCalledWith('/api/referral/campaigns/A1/supprimer', {}, expect.anything());
});

test('brouillon sans données : pas de mention « contient des données »', async () => {
  await monter([INV('D2', 'draft', 'event_free')]);
  await act(async () => { q('mes-inv-plus-D2').click(); });
  await act(async () => { q('mes-inv-supprimer-D2').click(); });
  await attendre(() => expect(q('mes-inv-supprimer-ok-D2').disabled).toBe(false));
  expect(q('mes-inv-supprimer-donnees-D2')).toBeNull();
});

test('Corbeille : repliée (aucun appel), puis liste les supprimées et « Restaurer en brouillon »', async () => {
  await monter([INV('A1', 'active')], [INV('X9', 'archived', 'pass_duo')]);
  const appelsAvant = axios.get.mock.calls.length;
  expect(q('mes-inv-corbeille-X9')).toBeNull();
  await act(async () => { q('mes-inv-corbeille-bouton').click(); });
  await attendre(() => expect(q('mes-inv-corbeille-X9')).toBeTruthy());
  expect(axios.get.mock.calls.length).toBe(appelsAvant + 1);
  expect(q('mes-inv-corbeille-A1')).toBeNull();
  axios.post.mockResolvedValue({ data: INV('X9', 'draft', 'pass_duo') });
  await act(async () => { q('mes-inv-restaurer-X9').click(); });
  expect(axios.post).toHaveBeenCalledWith('/api/referral/campaigns/X9/restaurer', {}, expect.anything());
});

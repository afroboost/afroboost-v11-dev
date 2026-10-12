/**
 * V610h — « Mes invitations » : Masquer (confirmation claire, rien supprimé) / Réactiver.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn(), create: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } }));
jest.mock('../EditeurInvitation', () => function E() { return null; });
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
const INV = (status) => ({ id: 'E1', type: 'event_paid', status, title: 'SILENT', share_url: 'https://afroboost.com/i/T', card_url: '/c.jpg' });

async function monter(status) {
  axios.get.mockResolvedValue({ data: { items: [INV(status)] } });
  conteneur = document.createElement('div'); document.body.appendChild(conteneur); racine = createRoot(conteneur);
  await act(async () => { racine.render(<MesInvitations API="/api" />); });
  await attendre(() => expect(q('mes-inv-E1')).toBeTruthy());
}

test('active : « Masquer » demande la confirmation exacte puis appelle /masquer', async () => {
  await monter('active');
  expect(q('mes-inv-reactiver-E1')).toBeNull();
  await act(async () => { q('mes-inv-plus-E1').click(); });
  await act(async () => { q('mes-inv-masquer-E1').click(); });
  const boite = q('mes-inv-masquer-confirmation-E1');
  expect(boite.textContent).toContain('Masquer cet événement ?');
  expect(boite.textContent).toContain('Il ne sera plus visible ni réservable, mais les réservations, paiements, statistiques et liens existants seront conservés.');
  expect(axios.post).not.toHaveBeenCalled();
  axios.post.mockResolvedValue({ data: INV('hidden') });
  await act(async () => { q('mes-inv-masquer-ok-E1').click(); });
  expect(axios.post).toHaveBeenCalledWith('/api/referral/campaigns/E1/masquer', {}, expect.anything());
});

test('masquée : statut « Masquée », bouton « Réactiver » -> /reactiver ; pas de « Masquer »', async () => {
  await monter('hidden');
  expect(q('mes-inv-statut-E1').textContent).toBe('Masquée');
  await act(async () => { q('mes-inv-plus-E1').click(); });
  expect(q('mes-inv-masquer-E1')).toBeNull();
  expect(q('mes-inv-modifier-menu-E1')).toBeTruthy();
  axios.post.mockResolvedValue({ data: INV('active') });
  await act(async () => { q('mes-inv-reactiver-E1').click(); });
  expect(axios.post).toHaveBeenCalledWith('/api/referral/campaigns/E1/reactiver', {}, expect.anything());
});

test('réactivation refusée (événement passé) : le message du serveur est affiché', async () => {
  await monter('hidden');
  axios.post.mockRejectedValue({ response: { status: 409, data: { detail: 'Cet événement est déjà passé : il ne peut pas être réactivé tel quel. Modifie sa date ou crée une nouvelle invitation.' } } });
  await act(async () => { q('mes-inv-reactiver-E1').click(); });
  await attendre(() => expect(q('mes-inv-E1').textContent).toContain('déjà passé'));
});

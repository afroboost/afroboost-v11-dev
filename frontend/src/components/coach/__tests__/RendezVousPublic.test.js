// V605 — page publique /rdv/<jeton> : date → heure → type → confirmation ; 409 = recharge.
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import RendezVousPublic from '../../RendezVousPublic';

jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;
const C = ['2026-10-13T07:00:00+00:00', '2026-10-13T07:30:00+00:00', '2026-10-14T12:00:00+00:00'];
let conteneur; let racine;
beforeEach(() => {
  axios.get.mockReset(); axios.post.mockReset();
  axios.get.mockResolvedValue({ data: { organisation: 'Stadtfest', deja_reserve: null, creneaux: C, duree_min: 30,
    types: [{ id: 'visio', libelle: 'Visio' }, { id: 'appel', libelle: 'Téléphone' }, { id: 'rencontre', libelle: 'Rencontre' }] } });
  conteneur = document.createElement('div'); document.body.appendChild(conteneur); racine = createRoot(conteneur);
});
afterEach(() => { act(() => racine.unmount()); conteneur.remove(); });
const attendre = async () => { for (let i = 0; i < 6; i += 1) await act(async () => { await Promise.resolve(); }); };
const q = (s) => document.querySelector(s);
const clic = async (el) => { await act(async () => { el.click(); }); await attendre(); };

test('date → heure (heure de Suisse) → type → confirmation', async () => {
  await act(async () => { racine.render(<RendezVousPublic token="abcdefghijklmnopqr" />); }); await attendre();
  expect(q('[data-testid="rdv-public"]').textContent).toContain('Prendre rendez-vous avec Coach Bassi');
  expect(document.querySelectorAll('[data-testid^="rdv-jour-"]').length).toBe(2);
  await clic(q('[data-testid="rdv-jour-2026-10-13"]'));
  const heures = [...document.querySelectorAll('[data-testid="rdv-heure"]')].map((b) => b.textContent);
  expect(heures).toEqual(['09:00', '09:30']);
  await clic(document.querySelectorAll('[data-testid="rdv-heure"]')[1]);
  await clic(q('[data-testid="rdv-type-appel"]'));
  axios.post.mockResolvedValue({ data: { confirme: true, rendez_vous: { starts_at: C[1], type_libelle: 'Téléphone', duree_min: 30 } } });
  await clic(q('[data-testid="rdv-confirmer"]'));
  expect(axios.post).toHaveBeenCalledWith('/api/public/rdv/abcdefghijklmnopqr', { starts_at: C[1], type: 'appel' });
  expect(q('[data-testid="rdv-confirme"]').textContent).toContain('Rendez-vous confirmé');
  expect(q('[data-testid="rdv-confirme"]').textContent).toContain('09:30');
});

test('créneau pris entre-temps (409) : message clair et créneaux rechargés', async () => {
  await act(async () => { racine.render(<RendezVousPublic token="abcdefghijklmnopqr" />); }); await attendre();
  await clic(q('[data-testid="rdv-jour-2026-10-13"]'));
  await clic(document.querySelectorAll('[data-testid="rdv-heure"]')[0]);
  axios.post.mockRejectedValue({ response: { status: 409, data: { detail: 'Ce créneau vient d’être réservé. Choisissez-en un autre.' } } });
  await clic(q('[data-testid="rdv-confirmer"]'));
  expect(q('[data-testid="rdv-envoi-erreur"]').textContent).toContain('vient d’être réservé');
  expect(axios.get).toHaveBeenCalledTimes(2);
  expect(q('[data-testid="rdv-confirme"]')).toBeNull();
});

test('lien déjà utilisé : affiche le rendez-vous existant, aucun nouveau choix', async () => {
  axios.get.mockResolvedValue({ data: { organisation: 'Troodi', deja_reserve: { starts_at: C[2], type_libelle: 'Visio', duree_min: 30 }, creneaux: [], types: [] } });
  await act(async () => { racine.render(<RendezVousPublic token="abcdefghijklmnopqr" />); }); await attendre();
  expect(q('[data-testid="rdv-confirme"]').textContent).toContain('14:00');
  expect(q('[data-testid="rdv-confirmer"]')).toBeNull();
});

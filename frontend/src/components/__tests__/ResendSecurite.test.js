// V608 — « Resend — Sécurité des envois » : ON/OFF, limite, seuil, confirmation avant OFF.
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import ResendSecurite from '../ResendSecurite';

jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn(), put: jest.fn() } }));
global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;
const ETAT = (actif, limite = 100, seuil = 95, n = 40) => ({ reglages: { actif, limite, seuil }, compte_effectif: n,
  restants_avant_seuil: Math.max(0, seuil - n), restants_avant_limite: Math.max(0, limite - n), plan_insuffisant: false });
let c; let racine;
beforeEach(() => { axios.get.mockReset(); axios.put.mockReset(); c = document.createElement('div'); document.body.appendChild(c); racine = createRoot(c); });
afterEach(() => { act(() => racine.unmount()); c.remove(); document.body.innerHTML = ''; });
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
const attendre = async () => { for (let i = 0; i < 6; i += 1) await act(async () => { await Promise.resolve(); }); };
const monter = async () => { await act(async () => { racine.render(<ResendSecurite API="/api" />); }); await attendre(); };

test('ON : limite, seuil et état actuel (comptabilisés, restants avant seuil / limite)', async () => {
  axios.get.mockResolvedValue({ data: ETAT(true) });
  await monter();
  expect(q('resend-limite').value).toBe('100');
  expect(q('resend-seuil').value).toBe('95');
  expect(q('resend-etat').textContent).toContain('40 envois comptabilisés');
  expect(q('resend-etat').textContent).toContain('55 restants avant seuil');
  expect(q('resend-etat').textContent).toContain('60 restants avant limite');
});

test('ON → OFF : confirmation obligatoire ; Annuler ne change rien ; Désactiver enregistre actif=false', async () => {
  axios.get.mockResolvedValue({ data: ETAT(true) });
  await monter();
  await act(async () => { q('resend-limitation').click(); });
  expect(q('resend-confirmation').textContent).toContain('Désactiver la limite Afroboost ?');
  expect(q('resend-confirmation').textContent).toContain('Les limites de votre abonnement Resend continueront de s’appliquer');
  await act(async () => { q('resend-annuler').click(); });
  expect(q('resend-confirmation')).toBeNull();
  expect(axios.put).not.toHaveBeenCalled();
  axios.put.mockResolvedValue({ data: { etat: ETAT(false) } });
  await act(async () => { q('resend-limitation').click(); });
  await act(async () => { q('resend-desactiver').click(); }); await attendre();
  expect(axios.put).toHaveBeenCalledWith('/api/admin/resend/reglages', { actif: false, limite: 100, seuil: 95 });
  expect(q('resend-off').textContent).toBe('Limitation Afroboost désactivée — les limites du compte Resend restent applicables.');
});

test('valeurs choisies (500 / 475) envoyées telles quelles ; OFF → ON sans confirmation', async () => {
  axios.get.mockResolvedValue({ data: ETAT(true) });
  await monter();
  const saisir = async (el, v) => { const s = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    await act(async () => { s.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); }); };
  await saisir(q('resend-limite'), '500'); await saisir(q('resend-seuil'), '475');
  axios.put.mockResolvedValue({ data: { etat: ETAT(true, 500, 475, 40) } });
  await act(async () => { q('resend-enregistrer').click(); }); await attendre();
  expect(axios.put).toHaveBeenLastCalledWith('/api/admin/resend/reglages', { actif: true, limite: 500, seuil: 475 });
  axios.get.mockResolvedValue({ data: ETAT(false) });
});

test('403 : message super-admin, aucun réglage affiché', async () => {
  axios.get.mockRejectedValue({ response: { status: 403 } });
  await monter();
  expect(q('resend-message').textContent).toContain('Réservé au super-admin');
  expect(q('resend-reglages')).toBeNull();
});

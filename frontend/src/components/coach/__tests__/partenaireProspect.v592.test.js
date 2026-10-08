// V592 — « Activer comme partenaire » depuis la fiche Prospect, vue du navigateur.
//
// Prouvé ici : le bouton n'apparaît que sans partenaire ; le slug proposé est
// celui de la règle existante ; l'activation envoie UN appel ; ensuite la fiche
// affiche « PARTENAIRE ACTIF » avec le lien, le QR et les résultats du système
// Partenaire EXISTANT (même composant, même URL, même route de statistiques).
// `axios` est mocké : aucun appel réseau.
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import PartenaireProspect from '../PartenaireProspect';
import { construireLienPartenaire } from '../../../utils/partnerLink';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));
jest.mock('qrcode.react', () => ({
  __esModule: true,
  QRCodeCanvas: ({ value, size }) => {
    const React = require('react');
    return React.createElement('canvas', { 'data-qr-value': value, width: size, height: size });
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

afterEach(() => {
  act(() => { racine.unmount(); });
  conteneur.remove();
  jest.resetAllMocks();
});

const STATS = {
  partner_slug: 'akoko_tresses_test', reservations: 1, unique_people: 1, attendances: 1,
  trials: 1, conversions: { total: 1, pulse: 0, member: 0, subscription: 1 },
  attendance_rate: 1, conversion_rate: 1,
};

function routerGet(partenaire) {
  axios.get.mockImplementation((url) => {
    if (url.endsWith('/partner')) return Promise.resolve({ data: { partner: partenaire } });
    if (url.includes('/stats')) return Promise.resolve({ data: STATS });
    return Promise.reject(new Error('inattendu ' + url));
  });
}

test('sans partenaire : bouton + slug proposé par la règle existante', async () => {
  routerGet(null);
  const c = await monter(<PartenaireProspect API="/api" prospectId="p-1"
                                             organisation="AKOKO TRESSES TEST" />);
  expect(c.querySelector('[data-testid="activer-partenaire"]').textContent)
    .toBe('Activer comme partenaire');
  expect(c.querySelector('[data-testid="partenaire-slug"]').value).toBe('akoko_tresses_test');
  expect(c.querySelector('[data-testid="partenaire-actif"]')).toBeNull();
  expect(axios.post).not.toHaveBeenCalled();
});

test('activation : UN appel, puis PARTENAIRE ACTIF + lien, QR et résultats existants', async () => {
  routerGet(null);
  const p = { id: 'x', partner_slug: 'akoko_tresses_test', partner_status: 'decouverte' };
  axios.post.mockResolvedValue({ data: { success: true, already: false, partner: p } });
  const onActive = jest.fn();
  const c = await monter(<PartenaireProspect API="/api" prospectId="p-1"
                                             organisation="AKOKO TRESSES TEST" onActive={onActive} />);
  await act(async () => { c.querySelector('[data-testid="activer-partenaire"]').click(); });
  expect(axios.post).toHaveBeenCalledTimes(1);
  expect(axios.post.mock.calls[0][0]).toBe('/api/partner-prospects/p-1/activate-partner');
  expect(axios.post.mock.calls[0][1]).toEqual({ partner_slug: 'akoko_tresses_test' });
  expect(onActive).toHaveBeenCalledWith(p);
  expect(c.textContent).toContain('PARTENAIRE ACTIF');
  const lien = c.querySelector('[data-testid="lien-partenaire"]').textContent;
  expect(lien).toBe(construireLienPartenaire('akoko_tresses_test'));
  expect(lien).toContain('utm_content=akoko_tresses_test');
  // QR existant
  const boutonQr = Array.from(c.querySelectorAll('button')).find((b) => b.textContent.includes('QR code'));
  await act(async () => { boutonQr.click(); });
  expect(c.querySelector('canvas').getAttribute('data-qr-value')).toBe(lien);
  expect(c.textContent).toContain('Télécharger le QR');
  // statistiques existantes, essais compris ; ni clics ni scans
  const tuiles = c.querySelector('[data-testid="p2d2-compteurs"]').textContent;
  expect(tuiles).toContain('Essais obtenus');
  expect(tuiles).toContain('Réservations');
  expect(tuiles).toContain('Présences');
  expect(tuiles).toContain('Conversions');
  expect(c.textContent).toContain('Taux de présence 100 %');
  expect(c.textContent).toContain('Taux de conversion 100 %');
  expect(c.textContent).not.toMatch(/clics|scans/i);
  expect(axios.get.mock.calls.some(([u]) => u === '/api/partners/akoko_tresses_test/stats')).toBe(true);
});

test('déjà partenaire : PARTENAIRE ACTIF directement, aucun bouton, aucune activation', async () => {
  routerGet({ id: 'x', partner_slug: 'akoko_tresses_test', partner_status: 'decouverte' });
  const c = await monter(<PartenaireProspect API="/api" prospectId="p-1" organisation="AKOKO" />);
  expect(c.textContent).toContain('PARTENAIRE ACTIF');
  expect(c.querySelector('[data-testid="activer-partenaire"]')).toBeNull();
  expect(axios.post).not.toHaveBeenCalled();
});

test('slug déjà pris : le message du serveur est affiché, rien ne passe en actif', async () => {
  routerGet(null);
  axios.post.mockRejectedValue({ response: { status: 409, data: { detail: 'Ce slug est déjà utilisé' } } });
  const c = await monter(<PartenaireProspect API="/api" prospectId="p-1" organisation="AKOKO" />);
  await act(async () => { c.querySelector('[data-testid="activer-partenaire"]').click(); });
  expect(c.querySelector('[data-testid="partenaire-message"]').textContent).toBe('Ce slug est déjà utilisé');
  expect(c.querySelector('[data-testid="partenaire-actif"]')).toBeNull();
});

test('slug invalide : refusé AVANT tout appel', async () => {
  routerGet(null);
  const c = await monter(<PartenaireProspect API="/api" prospectId="p-1" organisation="A" />);
  await act(async () => { c.querySelector('[data-testid="activer-partenaire"]').click(); });
  expect(axios.post).not.toHaveBeenCalled();
  expect(c.querySelector('[data-testid="partenaire-message"]')).not.toBeNull();
});

test('le composant de fiche ne contient aucun « P2 » visible', () => {
  const src = require('fs').readFileSync(require('path').join(__dirname, '..', 'PartenaireProspect.js'), 'utf8');
  const visibles = src.split('\n').filter((l) => !l.trim().startsWith('//')).join('\n');
  expect(visibles).not.toMatch(/['">]\s*P2\b/);
});

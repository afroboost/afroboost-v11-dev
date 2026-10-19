/**
 * V628 — « J'ai un code promo » sur un événement : lien discret, fenêtre, contrôles de saisie,
 * appel UNIQUE à /api/evenements/<offre>/place-code, aucun paiement. fetch est mocké : aucun réseau.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
// eslint-disable-next-line import/first
import CodePromoEvenement from '../CodePromoEvenement';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
jest.setTimeout(20000);
let conteneur = null; let racine = null;
function rendre(el) { conteneur = document.createElement('div'); document.body.appendChild(conteneur); racine = createRoot(conteneur); act(() => racine.render(el)); }
afterEach(() => {
  if (racine) act(() => racine.unmount());
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
  delete global.fetch;
  document.body.style.overflow = '';
});
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
async function attendre(fn) { let e; for (let i = 0; i < 100; i += 1) { try { fn(); return; } catch (x) { e = x; } await act(async () => { await new Promise((r) => setTimeout(r, 20)); }); } throw e; }
function saisir(id, valeur) {
  const el = q(id);
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  act(() => { setter.call(el, valeur); el.dispatchEvent(new Event('input', { bubbles: true })); });
}
function reponse(status, corps) { return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(corps) }); }
function fetchMock(place) {
  return jest.fn((url) => (String(url).endsWith('/api/concept') ? reponse(200, { termsText: 'Conditions test.' }) : place(url)));
}
function remplir(code = '28BOOSTHETAÏRA-01') {
  saisir('code-promo-evenement-prenom', 'Ana');
  saisir('code-promo-evenement-nom', 'Test');
  saisir('code-promo-evenement-email', 'ana@test.local');
  saisir('code-promo-evenement-code', code);
}
const valider = () => act(() => { q('code-promo-evenement-formulaire').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });

test('lien discret, fenêtre fermée par défaut, ouverture au clic', () => {
  global.fetch = fetchMock(() => reponse(200, {}));
  rendre(<CodePromoEvenement offreId="evt-1" titre="AFROBOOST SILENT" />);
  expect(q('code-promo-evenement-lien').textContent).toContain("J'ai un code promo");
  expect(q('code-promo-evenement-fenetre')).toBeNull();
  act(() => { q('code-promo-evenement-lien').click(); });
  expect(q('code-promo-evenement-fenetre')).not.toBeNull();
  expect(document.body.style.overflow).toBe('hidden');
  act(() => { q('code-promo-evenement-fermer').click(); });
  expect(q('code-promo-evenement-fenetre')).toBeNull();
});

test('conditions non cochées : refus local, aucun appel de réservation', async () => {
  global.fetch = fetchMock(() => reponse(200, { success: true }));
  rendre(<CodePromoEvenement offreId="evt-1" />);
  act(() => { q('code-promo-evenement-lien').click(); });
  remplir();
  valider();
  await attendre(() => expect(q('code-promo-evenement-erreur').textContent).toContain('conditions'));
  expect(global.fetch.mock.calls.filter(([u]) => String(u).includes('place-code'))).toHaveLength(0);
});

test('code valable : POST place-code (jamais Stripe), billet affiché', async () => {
  global.fetch = fetchMock(() => reponse(200, { success: true, deja_reserve: false, prix: 0,
    reservation: { reservationCode: 'AF12AB34CD', datetime: '2026-10-28T18:45:00' } }));
  rendre(<CodePromoEvenement offreId="evt-1" />);
  act(() => { q('code-promo-evenement-lien').click(); });
  remplir();
  act(() => { q('code-promo-evenement-conditions').click(); });
  valider();
  await attendre(() => expect(q('code-promo-evenement-succes')).not.toBeNull());
  const appels = global.fetch.mock.calls.filter(([u]) => String(u).includes('place-code'));
  expect(appels).toHaveLength(1);
  expect(appels[0][0]).toContain('/api/evenements/evt-1/place-code');
  const corps = JSON.parse(appels[0][1].body);
  expect(corps).toMatchObject({ prenom: 'Ana', nom: 'Test', email: 'ana@test.local', code: '28BOOSTHETAÏRA-01', terms_accepted: true });
  expect(global.fetch.mock.calls.some(([u]) => /stripe|checkout/i.test(String(u)))).toBe(false);
  expect(q('code-promo-evenement-billet').textContent).toContain('AF12AB34CD');
  expect(q('code-promo-evenement-succes').textContent).toMatch(/28 octobre 2026 à 18h45/i);
});

test('code refusé : le message du serveur est affiché tel quel', async () => {
  global.fetch = fetchMock(() => reponse(409, { detail: 'Ce code promo a déjà été utilisé.' }));
  rendre(<CodePromoEvenement offreId="evt-1" />);
  act(() => { q('code-promo-evenement-lien').click(); });
  remplir();
  act(() => { q('code-promo-evenement-conditions').click(); });
  valider();
  await attendre(() => expect(q('code-promo-evenement-erreur').textContent).toBe('Ce code promo a déjà été utilisé.'));
  expect(q('code-promo-evenement-succes')).toBeNull();
});

test('déjà inscrit : message dédié, aucun billet affiché', async () => {
  global.fetch = fetchMock(() => reponse(200, { success: true, deja_reserve: true, prix: 0,
    reservation: { datetime: '2026-10-28T18:45:00' } }));
  rendre(<CodePromoEvenement offreId="evt-1" />);
  act(() => { q('code-promo-evenement-lien').click(); });
  remplir();
  act(() => { q('code-promo-evenement-conditions').click(); });
  valider();
  await attendre(() => expect(q('code-promo-evenement-succes').textContent).toContain('déjà réservée'));
  expect(q('code-promo-evenement-billet')).toBeNull();
});

test('aperçu coach (inerte) : le lien ne s’ouvre pas', () => {
  global.fetch = fetchMock(() => reponse(200, {}));
  rendre(<CodePromoEvenement offreId="evt-1" inerte />);
  act(() => { q('code-promo-evenement-lien').click(); });
  expect(q('code-promo-evenement-fenetre')).toBeNull();
});

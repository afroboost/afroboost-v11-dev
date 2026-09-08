/**
 * F3 — L'ÉDITEUR DE PROFIL CROSS-APP, VU DU NAVIGATEUR.
 *
 * PROUVE (§15, §16) : chargement du profil réel, édition, enregistrement via
 * PATCH, double-clic protégé, erreur → texte conservé, non lié → refus doux,
 * et JAMAIS d'écriture d'un champ hors bio/city/sports.
 *
 * axios mocké : aucun réseau.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import axios from 'axios';
import EditeurProfilSpordateur from '../EditeurProfilSpordateur';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), patch: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));

let conteneur, racine;
beforeEach(() => { conteneur = document.createElement('div'); document.body.appendChild(conteneur); jest.clearAllMocks(); });
afterEach(() => { if (racine) act(() => racine.unmount()); conteneur.remove(); });
const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
// Saisie fiable dans un input/textarea CONTRÔLÉ par React : on passe par le
// setter natif, sinon le state React ne voit pas la nouvelle valeur.
function saisir(el, valeur) {
  const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
  setter.call(el, valeur);
  el.dispatchEvent(new Event('input', { bubbles: true }));
}

async function monter(getRep) {
  axios.get.mockReturnValue(getRep);
  await act(async () => { racine = createRoot(conteneur); racine.render(React.createElement(EditeurProfilSpordateur)); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
}
const PROFIL = { bio: 'Ancienne bio.', city: 'Neuchâtel', canton: 'NE', sports: [{ name: 'Tennis', level: 'advanced' }] };

test('A. lié → l’éditeur charge bio, ville, sports du profil réel', async () => {
  await monter(Promise.resolve({ data: { lie: true, profil: PROFIL } }));
  expect(par('champ-bio').value).toBe('Ancienne bio.');
  expect(par('champ-ville').value).toBe('Neuchâtel');
  expect(par('sport-Tennis')).toBeTruthy();
  expect(par('niveau-Tennis').value).toBe('advanced'); // le sport actif montre son niveau
});

test('B. enregistrer envoie un PATCH avec SEULEMENT bio/city/sports', async () => {
  await monter(Promise.resolve({ data: { lie: true, profil: PROFIL } }));
  axios.patch.mockResolvedValue({ data: { lie: true, profil: { ...PROFIL, bio: 'Nouvelle.' } } });
  await act(async () => { saisir(par('champ-bio'), 'Nouvelle.'); });
  await act(async () => { par('enregistrer-profil').click(); });
  await act(async () => { await Promise.resolve(); });
  expect(axios.patch).toHaveBeenCalledTimes(1);
  const [url, corps] = axios.patch.mock.calls[0];
  expect(url).toContain('/spordate/unified-profile/me');
  expect(Object.keys(corps.profil).sort()).toEqual(['bio', 'city', 'sports']);
  // aucun champ interdit n'est envoyé
  for (const c of ['credits', 'role', 'uid', 'isPremium', 'canton', 'displayName']) {
    expect(corps.profil[c]).toBeUndefined();
  }
  expect(par('editeur-message').textContent).toContain('enregistré');
});

test('C. sélectionner un sport puis choisir son niveau', async () => {
  await monter(Promise.resolve({ data: { lie: true, profil: { bio: '', city: '', sports: [] } } }));
  expect(par('niveau-Yoga')).toBeNull(); // inactif → pas de sélecteur
  await act(async () => { par('sport-Yoga').click(); });
  expect(par('niveau-Yoga')).toBeTruthy();
  await act(async () => { par('niveau-Yoga').value = 'intermediate'; par('niveau-Yoga').dispatchEvent(new Event('change', { bubbles: true })); });
  axios.patch.mockResolvedValue({ data: { lie: true, profil: { bio: '', city: '', sports: [{ name: 'Yoga', level: 'intermediate' }] } } });
  await act(async () => { par('enregistrer-profil').click(); });
  await act(async () => { await Promise.resolve(); });
  expect(axios.patch.mock.calls[0][1].profil.sports).toEqual([{ name: 'Yoga', level: 'intermediate' }]);
});

test('D. double clic → un seul PATCH', async () => {
  await monter(Promise.resolve({ data: { lie: true, profil: PROFIL } }));
  let debloquer;
  axios.patch.mockImplementation(() => new Promise((res) => { debloquer = res; }));
  await act(async () => { par('enregistrer-profil').click(); });
  expect(par('enregistrer-profil').disabled).toBe(true);
  await act(async () => { par('enregistrer-profil').click(); });
  expect(axios.patch).toHaveBeenCalledTimes(1);
  await act(async () => { debloquer({ data: { lie: true, profil: PROFIL } }); });
});

test('E. erreur API → message visible ET texte conservé', async () => {
  await monter(Promise.resolve({ data: { lie: true, profil: PROFIL } }));
  await act(async () => { saisir(par('champ-bio'), 'Texte précieux.'); });
  axios.patch.mockRejectedValue(new Error('réseau'));
  await act(async () => { par('enregistrer-profil').click(); });
  await act(async () => { await Promise.resolve(); });
  expect(par('editeur-message').textContent).toContain('conservé');
  expect(par('champ-bio').value).toBe('Texte précieux.'); // rien perdu
});

test('F. non lié → refus doux, aucun PATCH possible', async () => {
  await monter(Promise.resolve({ data: { lie: false, motif: 'non_lie' } }));
  expect(par('editeur-non-lie')).toBeTruthy();
  expect(par('champ-bio')).toBeNull();
  expect(axios.patch).not.toHaveBeenCalled();
});

test('G. pont indisponible → composant discret, espace intact', async () => {
  await monter(Promise.reject(new Error('down')));
  expect(par('editeur-profil')).toBeNull();
});

/**
 * V560 — menu rapide de l'espace abonné : icône + mot court, entrées absentes filtrées.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import MenuRapide from '../MenuRapide';

global.IS_REACT_ACT_ENVIRONMENT = true;

let conteneur, racine;
beforeEach(() => { conteneur = document.createElement('div'); document.body.appendChild(conteneur); });
afterEach(() => { act(() => racine.unmount()); conteneur.remove(); });

test('six raccourcis au plus, SVG + libellé ; une entrée null n’est pas rendue ; le clic transmet le bouton', async () => {
  const reserver = jest.fn();
  const entrees = [
    { id: 'reserver', libelle: 'Réserver', icone: 'calendar', onClick: reserver },
    { id: 'qr', libelle: 'Mon QR', icone: 'qrCode', onClick: jest.fn() },
    null,
    { id: 'createur', libelle: 'Créateur', icone: 'star', onClick: jest.fn() },
  ];
  await act(async () => { racine = createRoot(conteneur); racine.render(<MenuRapide entrees={entrees} />); });
  const boutons = conteneur.querySelectorAll('[data-testid="menu-rapide"] button');
  expect(Array.from(boutons).map((b) => b.textContent)).toEqual(['Réserver', 'Mon QR', 'Créateur']);
  boutons.forEach((b) => { expect(b.querySelector('svg')).not.toBeNull(); expect(parseInt(b.style.minHeight, 10)).toBeGreaterThanOrEqual(44); });
  await act(async () => { boutons[0].click(); });
  expect(reserver).toHaveBeenCalledWith(boutons[0]);
});

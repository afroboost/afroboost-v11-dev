/**
 * V630 — badges lisibles : texte sur aplat de marque adapté à la luminance, et badge
 * « Offre du moment » qui n'hérite plus du noir du `body`.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { onPrimary } from '../themeColor';
import { CarteOffreDuMoment } from '../../components/accueil/ColonneAccueil';

const act = React.act;

test('texte sur aplat : blanc sur couleur sombre, quasi-noir sur couleur claire', () => {
  expect(onPrimary('#9f2d70')).toBe('#fff'); // prune de la production
  expect(onPrimary('#D91CD2')).toBe('#fff'); // secours Afroboost
  expect(onPrimary('#FFD700')).toBe('#0a0a0a'); // jaune choisi par un coach
  expect(onPrimary('#f5c6e8')).toBe('#0a0a0a'); // rose pâle
  expect(onPrimary('illisible')).toBe('#fff');
});

test('badge de l’offre du moment : classe de couleur claire posée', () => {
  const host = document.createElement('div'); document.body.appendChild(host);
  const root = createRoot(host);
  act(() => { root.render(<CarteOffreDuMoment offre={{ id: 'x', name: 'SILENT' }} badge="Offre lancement" prix="25 CHF" onChoisir={() => {}} />); });
  const b = host.querySelector('[data-testid="accueil-offre-badge"]');
  expect(b.textContent).toBe('Offre lancement');
  expect(b.className).toContain('af-badge-doux');
  act(() => root.unmount()); host.remove();
});

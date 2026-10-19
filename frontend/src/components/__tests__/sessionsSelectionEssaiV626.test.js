/**
 * V626 — sélection d'une séance d'essai : « date puis horaire », créneau unique
 * sélectionné tout seul, « Continuer ma réservation ». Options FACULTATIVES :
 * sans elles, le calendrier « Sessions » est strictement celui d'avant.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import SessionsModal from '../SessionsModal';

jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn(() => Promise.resolve({ data: {} })), post: jest.fn() } }));

const act = React.act;
const j = (jour, h, m) => { const n = new Date(); return new Date(n.getFullYear(), n.getMonth() + 1, jour, h, m); };
// Jour 21 : UN créneau. Jour 23 : DEUX créneaux.
const OCC = [
  { id: 'c-mer', nom: 'Cours à l’unité', lieu: 'Chemin des Valangines 97, 2000 Neuchâtel', quand: j(21, 18, 45), ponctuel: false, offres: [] },
  { id: 'c-a', nom: 'Cours à l’unité', lieu: 'Salle A', quand: j(23, 10, 0), ponctuel: false, offres: [] },
  { id: 'c-b', nom: 'Cours à l’unité', lieu: 'Salle B', quand: j(23, 18, 30), ponctuel: false, offres: [] },
];
const ESSAI = { titre: 'Réserve ton cours d’essai gratuit', instruction: 'Choisis une date, puis un horaire.', etiquetteCreneau: 'Essai gratuit', selectionDirecte: true };

let host; let root;
const q = (s) => document.body.querySelector(s);
const qa = (s) => document.body.querySelectorAll(s);
function monter(props) {
  host = document.createElement('div'); document.body.appendChild(host); root = createRoot(host);
  act(() => { root.render(<SessionsModal open onClose={() => {}} occurrencesFournies={OCC} {...props} />); });
}
afterEach(() => { act(() => root.unmount()); host.remove(); jest.useRealTimers(); });

test('titre et consigne de l’essai gratuit', () => {
  monter({ onReserve: () => {}, ...ESSAI });
  expect(document.body.textContent).toContain('Réserve ton cours d’essai gratuit');
  expect(q('[data-testid="sessions-instruction"]').textContent).toBe('Choisis une date, puis un horaire.');
});

test('créneau unique : sélectionné tout seul, « Continuer » actif, étiquette « Essai gratuit » (pas « Cours à l’unité »)', () => {
  monter({ onReserve: () => {}, ...ESSAI });
  const c = q('[data-testid="sessions-creneau-0"]');
  expect(c.getAttribute('aria-checked')).toBe('true');
  expect(q('[data-testid="sessions-creneau-etiquette-0"]').textContent).toBe('Essai gratuit');
  expect(q('[data-testid="sessions-selection-directe"]').textContent).not.toContain('Cours à l’unité');
  expect(q('[data-testid="sessions-selection-directe"]').textContent).toContain('Chemin des Valangines 97');
  expect(q('[data-testid="sessions-continuer"]').disabled).toBe(false);
  expect(q('[data-testid="sessions-continuer"]').textContent).toBe('Continuer ma réservation');
});

test('« Continuer ma réservation » transmet EXACTEMENT le créneau choisi', () => {
  jest.useFakeTimers();
  const onReserve = jest.fn();
  monter({ onReserve, ...ESSAI });
  act(() => { q('[data-testid="sessions-continuer"]').click(); });
  act(() => { jest.advanceTimersByTime(100); });
  expect(onReserve).toHaveBeenCalledTimes(1);
  expect(onReserve.mock.calls[0][0].id).toBe('c-mer');
});

test('plusieurs horaires le même jour : rien d’imposé, la personne choisit', () => {
  monter({ onReserve: () => {}, ...ESSAI });
  const jour23 = Array.from(qa('[data-testid^="sessions-jour-"]')).find((b) => b.textContent.startsWith('23'));
  act(() => { jour23.click(); });
  expect(qa('[data-testid^="sessions-creneau-"][role="radio"]').length).toBe(2);
  expect(Array.from(qa('[role="radio"]')).every((b) => b.getAttribute('aria-checked') === 'false')).toBe(true);
  expect(q('[data-testid="sessions-date-choisie"]').textContent).toContain('choisis un horaire');
  expect(q('[data-testid="sessions-continuer"]').disabled).toBe(true);
  act(() => { q('[data-testid="sessions-creneau-1"]').click(); });
  expect(q('[data-testid="sessions-creneau-1"]').getAttribute('aria-checked')).toBe('true');
  expect(q('[data-testid="sessions-continuer"]').disabled).toBe(false);
});

test('SANS les options : calendrier d’origine (titre « Sessions », nom du cours, écran de détail)', () => {
  monter({ onReserve: () => {} });
  expect(document.body.textContent).toContain('Sessions');
  expect(q('[data-testid="sessions-selection-directe"]')).toBeNull();
  expect(q('[data-testid="sessions-instruction"]')).toBeNull();
  const carte = q('[data-testid="sessions-occurrence-0"]');
  expect(carte.textContent).toContain('Cours à l’unité');
  act(() => { carte.click(); });
  expect(q('[data-testid="sessions-detail"]')).not.toBeNull();
});

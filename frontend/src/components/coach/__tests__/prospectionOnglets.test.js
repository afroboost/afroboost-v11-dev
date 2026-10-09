// V595 — les 4 onglets « bientôt » deviennent des écrans. Aucun envoi : seuls des GET
// au chargement ; une écriture n'existe que sur un geste explicite (Médias / Liens).
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import ProspectionApercu from '../prospection/ProspectionApercu';
import ProspectionResultats from '../prospection/ProspectionResultats';
import ProspectionMedias from '../prospection/ProspectionMedias';
import ProspectionLiens from '../prospection/ProspectionLiens';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), patch: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const FICHES = [
  { id: 'a', ref: 'GV-D-34', status: 'a_contacter', category: 'ecole_danse', city: 'Paris (France)', wave: 'GV 10-2026 — D Écoles de danse France', preferred_channel: 'E-mail', created_at: '2026-10-09T05:00:00+00:00' },
  { id: 'b', ref: 'COM-01', status: 'contacte', category: 'commerce', city: 'Neuchâtel', wave: 'Vague 1', preferred_channel: 'Visite / DM', first_contact_sent_at: '2026-09-03T08:00:00+00:00', created_at: '2026-08-31T18:26:57+00:00' },
  { id: 'c', ref: 'ETU-01', status: 'repondu', category: 'communaute_etudiante', city: 'Neuchâtel', wave: 'Vague 2', preferred_channel: 'DM', first_contact_sent_at: '2026-09-03T08:00:00+00:00', replied_at: '2026-09-04T05:00:00+00:00', created_at: '2026-08-31T18:26:57+00:00' },
];

function routeur(url) {
  if (url.endsWith('/partner-prospects')) return { data: { total: FICHES.length, prospects: FICHES } };
  if (url.endsWith('/calendar-events')) return { data: { events: [] } };
  if (url.endsWith('/prospect-inbound')) return { data: { conversations_total: 7, conversations_counts: { refus: 1 } } };
  if (url.endsWith('/prospection-medias')) return { data: { total: 0, medias: [], defaut_par_niche: {} } };
  if (url.endsWith('/prospection-liens')) return { data: { total: 0, liens: [] } };
  return { data: {} };
}

let conteneur; let racine;
beforeEach(() => {
  axios.get.mockReset(); axios.post.mockReset(); axios.patch.mockReset();
  axios.get.mockImplementation((url) => Promise.resolve(routeur(url)));
  conteneur = document.createElement('div'); document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
});
afterEach(() => { act(() => racine.unmount()); conteneur.remove(); });

async function monter(el) {
  await act(async () => { racine.render(el); });
  for (let i = 0; i < 6; i += 1) await act(async () => { await Promise.resolve(); });
}
const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);

test('Vue d\'ensemble : chiffres réels, aucune écriture', async () => {
  await monter(<ProspectionApercu API="/api" />);
  expect(par('prospection-apercu')).toBeTruthy();
  expect(par('pp-total').textContent).toContain('3');
  expect(par('pp-france').textContent).toContain('1');
  expect(par('pp-suisse').textContent).toContain('2');
  expect(par('pp-conversations').textContent).toContain('7');
  expect(par('pp-conversations').textContent).toContain('1 marquée(s) « refus »');
  expect(conteneur.querySelectorAll('[data-testid="pp-niches-ligne"]').length).toBe(6);
  expect(axios.post).not.toHaveBeenCalled();
  expect(axios.patch).not.toHaveBeenCalled();
});

test('Résultats : entonnoir, taux, période vide = 0', async () => {
  await monter(<ProspectionResultats API="/api" />);
  expect(par('pr-etape-contacte').textContent).toBe('2');
  expect(par('pr-etape-reponse').textContent).toBe('1');
  expect(par('pr-taux').textContent).toContain('50 %');
  expect(par('pr-taux').textContent).toContain('—');
  await act(async () => { par('pr-periode-7j').click(); });
  expect(par('pr-etape-contacte').textContent).toBe('0');
  await act(async () => { par('pr-comparer-niche_pays').click(); });
  expect(par('pr-comparaison').textContent).toContain('Écoles de danse France');
  expect(axios.post).not.toHaveBeenCalled();
});

test('Médias : 6 niches « En cours », 0 validée, aucune écriture à l\'ouverture', async () => {
  await monter(<ProspectionMedias API="/api" />);
  ['A', 'B', 'C', 'D', 'E', 'F'].forEach((n) => expect(par(`pm-statut-niche-${n}`).textContent).toBe('En cours'));
  expect(par('pm-validees').textContent).toBe('0');
  expect(conteneur.textContent).not.toMatch(/Supprimer/);
  expect(axios.post).not.toHaveBeenCalled();
});

test('Liens : vide, bandeau de blocage, aucune écriture à l\'ouverture', async () => {
  await monter(<ProspectionLiens API="/api" />);
  expect(par('pl-bandeau').textContent).toMatch(/bloqués par le serveur/);
  expect(par('pl-vide')).toBeTruthy();
  expect(conteneur.textContent).not.toMatch(/Supprimer/);
  expect(axios.post).not.toHaveBeenCalled();
});

/**
 * INV-3 — la séance d'une invitation n'est JAMAIS coupée par la limite
 * d'affichage de l'espace participant (12 séances).
 *
 * Le serveur ajoute la séance invitée à `upcoming_courses` (J+15..J+30) quand
 * elle est autorisée ; l'écran l'affiche via `seancesVisibles` — une seule
 * fonction pour l'affichage ET la présélection. Aucune réservation automatique.
 */
import fs from 'fs';
import path from 'path';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import SubscriberSpace from '../SubscriberSpace';
import { seancesVisibles, SEANCES_VISIBLES_MAX } from '../../utils/invitationSeance';

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('axios', () => ({
  __esModule: true,
  default: {
    get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn(),
    interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } },
  },
}));
jest.mock('../ConditionsParticipation', () => () => null);
jest.mock('../ConversionApresEssai', () => () => null);
jest.mock('../SubscriberOnboarding', () => () => null);
jest.mock('../SubscriberCockpit', () => () => null);
jest.mock('../SvgIcon', () => () => null);
jest.mock('../InvitationTemoignage', () => ({
  __esModule: true, default: () => null, enRepos: () => false
}));
jest.mock('../Publications', () => ({ PublishModal: () => null }));
jest.mock('qrcode.react', () => ({ QRCodeSVG: () => null }));
jest.mock('../ui/dialog', () => ({
  Dialog: ({ children }) => children,
  DialogContent: ({ children }) => children,
  DialogTitle: ({ children }) => children,
}));

const CODE = 'AFR-INV3AA';
const p = (n) => String(n).padStart(2, '0');
/** « AAAA-MM-JJTHH:MM:00 » (naïf local, convention du serveur) dans N jours. */
function occ(jours, heure = '18:30') {
  const d = new Date(Date.now() + jours * 86400000);
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${heure}:00`;
}
function ligne(courseId, datetime, extra = {}) {
  return { course_id: courseId, name: `Cours ${courseId}`, datetime,
    date: datetime.slice(0, 10), time: datetime.slice(11, 16), ...extra };
}
/** 14 séances quotidiennes (J+1..J+14) : la liste coupée à 12 de l'écran. */
const QUATORZE = Array.from({ length: 14 }, (_, i) => ligne(`c-${i + 1}`, occ(i + 1, '07:00')));
const J21 = occ(21);

// ═══════════════════════════════════════════════════════════════════════════
describe('INV-3 A — seancesVisibles (règle pure)', () => {
  test('12 premières par défaut, comme avant', () => {
    expect(SEANCES_VISIBLES_MAX).toBe(12);
    expect(seancesVisibles(QUATORZE, null)).toEqual(QUATORZE.slice(0, 12));
    expect(seancesVisibles(QUATORZE)).toEqual(QUATORZE.slice(0, 12));
  });

  test('invitée au-delà du 12e rang -> les 12 + elle, jamais coupée', () => {
    const liste = [...QUATORZE, ligne('c-soir', J21)];
    const v = seancesVisibles(liste, { course: 'c-soir', occurrence: J21.slice(0, 16) });
    expect(v).toHaveLength(13);
    expect(v.slice(0, 12)).toEqual(liste.slice(0, 12));
    expect(v[12]).toBe(liste[14]);
  });

  test('13e rang exact (index 12) -> ajoutée une seule fois', () => {
    const v = seancesVisibles(QUATORZE, { course: 'c-13', occurrence: QUATORZE[12].datetime.slice(0, 16) });
    expect(v).toHaveLength(13);
    expect(v[12]).toBe(QUATORZE[12]);
  });

  test('invitée déjà dans les 12 -> liste inchangée', () => {
    const v = seancesVisibles(QUATORZE, { course: 'c-3', occurrence: QUATORZE[2].datetime.slice(0, 16) });
    expect(v).toEqual(QUATORZE.slice(0, 12));
  });

  test('invitée absente / billet séparé / entrée invalide -> 12 premières', () => {
    expect(seancesVisibles(QUATORZE, { course: 'c-x', occurrence: J21.slice(0, 16) }))
      .toEqual(QUATORZE.slice(0, 12));
    const evt = [...QUATORZE, ligne('c-evt', J21, { inclus_abonnement: false })];
    expect(seancesVisibles(evt, { course: 'c-evt', occurrence: J21.slice(0, 16) }))
      .toEqual(evt.slice(0, 12));
    expect(seancesVisibles(null, null)).toEqual([]);
    expect(seancesVisibles(undefined, { course: 'c-1', occurrence: 'x' })).toEqual([]);
  });

  test('liste courte : inchangée', () => {
    const court = QUATORZE.slice(0, 3);
    expect(seancesVisibles(court, { course: 'c-2', occurrence: court[1].datetime.slice(0, 16) })).toEqual(court);
  });
});

// ═══════════════════════════════════════════════════════════════════════════
function espace(cours) {
  return {
    subscriber: { name: 'Ana Dupont', code: CODE, whatsapp: '+41760000000' },
    subscription: { id: 'sub-1', code: CODE, offer_name: 'Cours d\'essai',
      total_sessions: 1, remaining_sessions: 1, used_sessions: 0 },
    coach: { name: 'Afroboost' },
    upcoming_courses: cours,
    reservations: [],
    trial: { is_trial: true, state: 'available' },
  };
}

let conteneur;
let racine;

async function monter(reponse, search) {
  window.history.replaceState({}, '', `/espace/${CODE}${search || ''}`);
  axios.get.mockResolvedValue({ data: reponse });
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  await act(async () => {
    racine = createRoot(conteneur);
    racine.render(<SubscriberSpace accessCode={CODE} />);
  });
}
const parTestId = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const boutons = () => Array.from(conteneur.querySelectorAll('[data-testid^="seance-date-"]'));
const indexSelectionne = () => boutons().findIndex((b) => b.getAttribute('aria-pressed') === 'true');
const q = (course, occurrence) =>
  `?course=${encodeURIComponent(course)}&occurrence=${encodeURIComponent(occurrence)}`;
const appelsEspace = () => axios.get.mock.calls
  .map((c) => String(c[0]))
  .filter((u) => u.includes(`/subscriber/space/${encodeURIComponent(CODE)}`));

beforeEach(() => {
  jest.clearAllMocks();
  window.localStorage.setItem('afroboost_espace_token', JSON.stringify({
    token: 'jeton-de-banc', code: CODE, slug: '',
    expires_at: new Date(Date.now() + 30 * 86400000).toISOString(),
  }));
});

afterEach(async () => {
  if (racine) await act(async () => racine.unmount());
  if (conteneur && conteneur.parentNode) conteneur.remove();
  window.history.replaceState({}, '', '/');
});

describe('INV-3 B — espace : la séance invitée au-delà des 12', () => {
  test('J+21 (ajoutée par le serveur en fin de liste) : affichée et présélectionnée', async () => {
    await monter(espace([...QUATORZE, ligne('c-soir', J21)]), q('c-soir', J21.slice(0, 16)));
    expect(boutons()).toHaveLength(13);
    expect(indexSelectionne()).toBe(12);
    expect(parTestId('inv2-seance-invitation')).not.toBeNull();
    expect(parTestId('inv2-seance-indisponible')).toBeNull();
    expect(parTestId('reserve-c-soir')).not.toBeNull();
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('13e rang : présélectionnée (plus de faux « indisponible »)', async () => {
    await monter(espace(QUATORZE), q('c-13', QUATORZE[12].datetime.slice(0, 16)));
    expect(boutons()).toHaveLength(13);
    expect(indexSelectionne()).toBe(12);
    expect(parTestId('inv2-seance-indisponible')).toBeNull();
    expect(parTestId('reserve-c-13')).not.toBeNull();
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('sans paramètre : 12 séances, la première, comme avant', async () => {
    await monter(espace([...QUATORZE, ligne('c-soir', J21)]), '');
    expect(boutons()).toHaveLength(12);
    expect(indexSelectionne()).toBe(0);
    expect(parTestId('inv2-seance-invitation')).toBeNull();
  });

  test('séance refusée par le serveur (absente) : message INV-2, choix normal', async () => {
    await monter(espace(QUATORZE), q('c-soir', J21.slice(0, 16)));
    expect(boutons()).toHaveLength(12);
    expect(parTestId('inv2-seance-indisponible')).not.toBeNull();
    expect(indexSelectionne()).toBe(0);
  });
});

describe('INV-3 C — la requête transmet course/occurrence, une seule lecture', () => {
  test('avec invitation : ?course=&occurrence= dans l URL de l espace', async () => {
    await monter(espace(QUATORZE), q('c-soir', J21.slice(0, 16)));
    const urls = appelsEspace();
    expect(urls).toHaveLength(1);
    expect(urls[0]).toContain(`course=c-soir`);
    expect(urls[0]).toContain(`occurrence=${encodeURIComponent(J21.slice(0, 16))}`);
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('sans invitation (ou paramètre malformé) : URL strictement d avant', async () => {
    await monter(espace(QUATORZE), '');
    expect(appelsEspace()).toEqual([expect.stringMatching(new RegExp(`/subscriber/space/${CODE}$`))]);
    await act(async () => racine.unmount());
    conteneur.remove();
    jest.clearAllMocks();
    await monter(espace(QUATORZE), `?course=c-soir&occurrence=${J21.slice(0, 10)}`);
    expect(appelsEspace()).toEqual([expect.stringMatching(new RegExp(`/subscriber/space/${CODE}$`))]);
  });

  test('la présélection et l affichage passent par la MÊME fonction pure', () => {
    const src = fs.readFileSync(path.join(__dirname, '..', 'SubscriberSpace.js'), 'utf8');
    expect(src).not.toMatch(/courses\.slice\(0,\s*12\)/);
    expect(src).not.toMatch(/upcoming_courses \|\| \[\]\)\.slice\(0,\s*12\)/);
    expect((src.match(/seancesVisibles\(/g) || []).length).toBeGreaterThanOrEqual(2);
  });
});

/**
 * INV-2 — BANC DOM RÉEL : la séance d'une invitation arrive PRÉSÉLECTIONNÉE
 * dans le sélecteur EXISTANT de l'espace participant (`selectedCourseIdx`).
 *
 * Parcours réel : /api/share/invite/<jeton> -> `/?offre=&reserver=1&course=&occurrence=`
 * -> formulaire gratuit -> POST /checkout/free -> `/espace/AFR-XXXXXX?course=&occurrence=`
 * (cibleAvecSeance) -> CE composant. Aucune réservation automatique : aucun POST.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import SubscriberSpace from '../SubscriberSpace';

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

const CODE = 'AFR-2287CA';

/** « 2026-10-01T18:30:00 » (naïf local, convention du serveur) dans N jours. */
function occ(jours, heure = '18:30') {
  const d = new Date(Date.now() + jours * 86400000);
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${heure}:00`;
}
const S1 = occ(2);
const S2 = occ(9);
const PASSEE = occ(-3);

function ligne(courseId, datetime, extra = {}) {
  return { course_id: courseId, name: `Cours ${courseId}`, datetime,
    date: datetime.slice(0, 10), time: datetime.slice(11, 16), ...extra };
}

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
/** L'index du bouton de date présélectionné (aria-pressed="true"). */
const indexSelectionne = () => {
  const boutons = Array.from(conteneur.querySelectorAll('[data-testid^="seance-date-"]'));
  return boutons.findIndex((b) => b.getAttribute('aria-pressed') === 'true');
};
const q = (course, occurrence) =>
  `?course=${encodeURIComponent(course)}&occurrence=${encodeURIComponent(occurrence)}`;

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

describe('INV-2 A — essai avec séance : présélectionnée, rien de réservé', () => {
  test('la séance de l invitation est sélectionnée et annoncée', async () => {
    await monter(espace([ligne('c-42', S1)]), q('c-42', S1.slice(0, 16)));
    expect(indexSelectionne()).toBe(0);
    expect(parTestId('inv2-seance-invitation')).not.toBeNull();
    expect(parTestId('inv2-seance-indisponible')).toBeNull();
    expect(parTestId('reserve-c-42')).not.toBeNull();
    // Aucune réservation automatique : la personne clique elle-même.
    expect(axios.post).not.toHaveBeenCalled();
  });
});

describe('INV-2 B — deux séances : celle de l invitation, pas la première', () => {
  test('même cours, deux dates : la 2e est présélectionnée', async () => {
    await monter(espace([ligne('c-42', S1), ligne('c-42', S2)]), q('c-42', S2.slice(0, 16)));
    expect(indexSelectionne()).toBe(1);
    expect(parTestId('inv2-seance-invitation')).not.toBeNull();
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('deux cours : le bon cours est présélectionné', async () => {
    await monter(espace([ligne('c-1', S1), ligne('c-2', S1)]), q('c-2', S1.slice(0, 16)));
    expect(indexSelectionne()).toBe(1);
    expect(parTestId('reserve-c-2')).not.toBeNull();
    expect(parTestId('reserve-c-1')).toBeNull();
  });

  test('sans paramètre : comportement d avant (la première), aucun bandeau', async () => {
    await monter(espace([ligne('c-42', S1), ligne('c-42', S2)]), '');
    expect(indexSelectionne()).toBe(0);
    expect(parTestId('inv2-seance-invitation')).toBeNull();
    expect(parTestId('inv2-seance-indisponible')).toBeNull();
  });
});

describe('INV-2 C — séance invalide : message clair, choix normal', () => {
  const liste = () => espace([ligne('c-42', S1), ligne('c-42', S2)]);

  test.each([
    ['occurrence passée (absente de la liste du serveur)', q('c-42', PASSEE.slice(0, 16))],
    ['cours inconnu / supprimé', q('c-inconnu', S2.slice(0, 16))],
    ['occurrence non proposée par le cours', q('c-42', `${S2.slice(0, 10)}T07:15`)],
  ])('%s -> message, rien de présélectionné à tort', async (_nom, search) => {
    await monter(liste(), search);
    expect(parTestId('inv2-seance-indisponible')).not.toBeNull();
    expect(parTestId('inv2-seance-indisponible').textContent)
      .toContain('La séance de ton invitation n’est plus disponible. Choisis une autre séance ci-dessous.');
    expect(parTestId('inv2-seance-invitation')).toBeNull();
    expect(indexSelectionne()).toBe(0);   // le choix normal, comme avant
  });

  test('billet séparé (inclus_abonnement false) -> indisponible ici', async () => {
    await monter(espace([ligne('c-42', S1), ligne('c-evt', S2, { inclus_abonnement: false })]),
      q('c-evt', S2.slice(0, 16)));
    expect(parTestId('inv2-seance-indisponible')).not.toBeNull();
    expect(indexSelectionne()).toBe(0);
  });

  test.each([
    ['cours hors motif', `?course=${encodeURIComponent('a b/c')}&occurrence=${encodeURIComponent(S2.slice(0, 16))}`],
    ['occurrence date seule', `?course=c-42&occurrence=${S2.slice(0, 10)}`],
    ['occurrence avec secondes', `?course=c-42&occurrence=${encodeURIComponent(S2)}`],
    ['un seul des deux paramètres', `?course=c-42`],
  ])('paramètre malformé (%s) -> ignoré, parcours d avant', async (_nom, search) => {
    await monter(liste(), search);
    expect(parTestId('inv2-seance-invitation')).toBeNull();
    expect(parTestId('inv2-seance-indisponible')).toBeNull();
    expect(indexSelectionne()).toBe(0);
  });
});

describe('INV-2 D — événement gratuit : le bon événement', () => {
  test('date fixe (is_fixed_date) parmi d autres séances', async () => {
    const EVT = occ(5, '20:00');
    await monter(espace([
      ligne('c-42', S1),
      ligne('evt-gala', EVT, { is_fixed_date: true, name: 'Gala Afro' }),
      ligne('c-42', S2),
    ]), q('evt-gala', EVT.slice(0, 16)));
    expect(indexSelectionne()).toBe(1);
    expect(parTestId('reserve-evt-gala')).not.toBeNull();
    expect(parTestId('inv2-seance-libelle').textContent).toContain('20:00');
    expect(axios.post).not.toHaveBeenCalled();
  });
});

describe('INV-2 — usage unique : un rechargement des données ne rejoue pas', () => {
  test('la personne change de séance, la présélection ne revient pas', async () => {
    await monter(espace([ligne('c-42', S1), ligne('c-42', S2)]), q('c-42', S2.slice(0, 16)));
    expect(indexSelectionne()).toBe(1);
    const b0 = conteneur.querySelector('[data-testid="seance-date-0"]');
    await act(async () => { b0.click(); });
    expect(indexSelectionne()).toBe(0);
    expect(axios.get.mock.calls.length).toBeLessThanOrEqual(3);
  });
});

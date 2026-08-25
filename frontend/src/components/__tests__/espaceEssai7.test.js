/**
 * ESSAI-7 — BANC DOM REEL de l'espace participant.
 *
 * Les autres bancs de ce lot lisent le code comme du texte. Celui-ci MONTE
 * vraiment le composant dans un DOM (jsdom), clique vraiment sur le bouton, et
 * regarde ce qui est rendu. C'est la seule facon de prouver trois choses qu'une
 * lecture de source ne prouve pas :
 *
 *   1. l'ordre REELLEMENT calcule des blocs (`order` en CSS) ;
 *   2. `session_booked` part UNE fois, apres la reponse du serveur, et ne se
 *      rejoue pas au re-rendu ;
 *   3. un forfait payant ne voit RIEN de tout cela.
 *
 * Aucun reseau : `axios` est un mouchard. Les composants lourds (QR, modale,
 * cockpit) sont neutralises — ce banc juge la structure de l'ecran d'essai, pas
 * leur rendu interne.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import SubscriberSpace from '../SubscriberSpace';

// React 19 exige ce drapeau pour reconnaitre `act()` hors d'un harnais dedie.
// Sans lui, chaque rendu ecrit un avertissement et la sortie n'est plus lisible.
global.IS_REACT_ACT_ENVIRONMENT = true;

// Fabrique explicite : le vrai `axios` est publie en ESM et jest ne sait pas
// le charger ici. On ne veut de toute facon AUCUN reseau.
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
const DEMAIN = new Date(Date.now() + 36 * 3600 * 1000).toISOString();

function espace({ trial, reservations = [], cours = null, restantes = 1 }) {
  return {
    subscriber: { name: 'Ana Dupont', code: CODE, whatsapp: '+41760000000' },
    subscription: {
      id: 'sub-1', code: CODE, offer_name: 'Cours d\'essai',
      total_sessions: 1, remaining_sessions: restantes, used_sessions: 1 - restantes
    },
    coach: { name: 'Afroboost' },
    upcoming_courses: cours === null
      ? [{ course_id: 'c-42', name: 'Afroboost Pulse', datetime: DEMAIN,
           date: DEMAIN.slice(0, 10), time: '18:30' }]
      : cours,
    reservations,
    trial,
  };
}

let conteneur;
let racine;
let ph;

async function monter(reponse) {
  axios.get.mockResolvedValue({ data: reponse });
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  await act(async () => {
    racine = createRoot(conteneur);
    racine.render(<SubscriberSpace accessCode={CODE} />);
  });
}

const parTestId = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const ordreDe = (id) => {
  const el = parTestId(id);
  return el ? Number(el.style.order || 0) : null;
};

beforeEach(() => {
  ph = { capture: jest.fn() };
  window.posthog = ph;
  window.history.replaceState({}, '', `/espace/${CODE}`);
  jest.clearAllMocks();
});

afterEach(async () => {
  if (racine) await act(async () => racine.unmount());
  if (conteneur && conteneur.parentNode) conteneur.remove();
  delete window.posthog;
});

// ==========================================================================
describe('essai accorde, aucune seance choisie', () => {
  beforeEach(async () => {
    await monter(espace({ trial: { is_trial: true, state: 'available' } }));
  });

  test('l annonce et la reservation passent AVANT le QR', () => {
    expect(parTestId('essai7-priorite')).not.toBeNull();
    // negatif = remonte ; le QR reste a sa place, donc a 0
    expect(ordreDe('essai7-priorite')).toBeLessThan(0);
    expect(ordreDe('subscriber-space-reservation')).toBeLessThan(0);
    expect(ordreDe('subscriber-space-qr')).toBe(0);
    // l'entete reste au-dessus de tout
    expect(ordreDe('subscriber-space-header'))
      .toBeLessThan(ordreDe('essai7-priorite'));
  });

  test('le QR reste accessible — il est relegue, jamais retire', () => {
    expect(parTestId('subscriber-space-qr')).not.toBeNull();
  });

  test('l ecran dit ce qu il faut faire maintenant', () => {
    const texte = parTestId('essai7-priorite').textContent;
    expect(texte).toContain("Ton cours d'essai est activé");
    expect(texte).toContain('Choisis maintenant ta séance');
  });

  test('aucune confirmation de seance n est affichee', () => {
    expect(parTestId('essai7-reserve')).toBeNull();
  });
});

// ==========================================================================
describe('aucun creneau reservable', () => {
  test('dit la verite et ne promet aucune notification', async () => {
    await monter(espace({ trial: { is_trial: true, state: 'available' }, cours: [] }));
    const vide = parTestId('essai7-aucun-creneau');
    expect(vide).not.toBeNull();
    expect(vide.textContent).toContain('Aucun nouveau créneau');
    expect(vide.textContent).not.toMatch(/pr[ée]viendr|notifier|alerte/i);
    // l'espace reste entierement accessible
    expect(parTestId('subscriber-space-qr')).not.toBeNull();
  });
});

// ==========================================================================
describe('la seance est reservee', () => {
  beforeEach(async () => {
    await monter(espace({
      trial: { is_trial: true, state: 'booked' },
      reservations: [{ id: 'r-1', courseId: 'c-42', datetime: DEMAIN,
                       courseName: 'Afroboost Pulse' }],
      restantes: 0,
    }));
  });

  test('l etat reserve domine, avec le QR comme suite', () => {
    const bloc = parTestId('essai7-reserve');
    expect(bloc).not.toBeNull();
    expect(bloc.textContent).toContain('Ta séance est réservée');
    expect(bloc.textContent).toContain('Présente-le au coach');
    expect(ordreDe('essai7-reserve')).toBeLessThan(0);
    // la reservation redescend a sa place : le choix est fait
    expect(ordreDe('subscriber-space-reservation')).toBe(0);
  });

  test('le CTA ouvre le QR sans le deplacer', () => {
    expect(parTestId('essai7-voir-qr')).not.toBeNull();
    expect(parTestId('subscriber-space-qr')).not.toBeNull();
  });

  test('plus aucune invitation a choisir une seance', () => {
    expect(parTestId('essai7-priorite')).toBeNull();
  });
});

// ==========================================================================
describe('session_booked — une fois, au bon moment', () => {
  test('rien n est emis a l affichage', async () => {
    await monter(espace({ trial: { is_trial: true, state: 'available' } }));
    expect(ph.capture).not.toHaveBeenCalled();
  });

  test('emis UNE fois apres la confirmation du serveur, sans donnee personnelle',
    async () => {
      await monter(espace({ trial: { is_trial: true, state: 'available' } }));
      axios.post.mockResolvedValue({
        data: { reservation: { id: 'r-9', courseId: 'c-42', datetime: DEMAIN },
                remaining_sessions: 0 }
      });

      await act(async () => { parTestId('reserve-c-42').click(); });

      const appels = ph.capture.mock.calls.filter((c) => c[0] === 'session_booked');
      expect(appels).toHaveLength(1);
      expect(appels[0][1]).toEqual({ course_id: 'c-42', places: 1, is_trial: true });
      // ni code, ni prenom, ni adresse
      expect(JSON.stringify(appels[0][1])).not.toContain('AFR-');
      expect(JSON.stringify(appels[0][1])).not.toContain('Ana');
    });

  test('une reservation REFUSEE par le serveur ne compte pas', async () => {
    await monter(espace({ trial: { is_trial: true, state: 'available' } }));
    axios.post.mockRejectedValue({ response: { status: 409, data: { detail: 'Déjà réservé.' } } });

    await act(async () => { parTestId('reserve-c-42').click(); });

    expect(ph.capture.mock.calls.filter((c) => c[0] === 'session_booked')).toHaveLength(0);
  });

  test('un re-rendu ne rejoue pas l evenement', async () => {
    await monter(espace({ trial: { is_trial: true, state: 'available' } }));
    axios.post.mockResolvedValue({ data: { reservation: { id: 'r-9', courseId: 'c-42', datetime: DEMAIN } } });
    await act(async () => { parTestId('reserve-c-42').click(); });
    await act(async () => { racine.render(<SubscriberSpace accessCode={CODE} />); });

    expect(ph.capture.mock.calls.filter((c) => c[0] === 'session_booked')).toHaveLength(1);
  });

  test('l ecran bascule en « reservee » sans rechargement', async () => {
    await monter(espace({ trial: { is_trial: true, state: 'available' } }));
    axios.post.mockResolvedValue({
      data: { reservation: { id: 'r-9', courseId: 'c-42', datetime: DEMAIN,
                             courseName: 'Afroboost Pulse' }, remaining_sessions: 0 }
    });

    await act(async () => { parTestId('reserve-c-42').click(); });

    expect(parTestId('essai7-reserve')).not.toBeNull();
    expect(parTestId('essai7-priorite')).toBeNull();
    // le serveur n'a PAS ete rappele : l'etat a avance tout seul
    expect(axios.get).toHaveBeenCalledTimes(1);
  });
});

// ==========================================================================
describe('un forfait payant ne voit rien de tout cela', () => {
  beforeEach(async () => {
    await monter(espace({ trial: { is_trial: false }, restantes: 8 }));
  });

  test('aucun bloc d essai, aucun reordonnancement', () => {
    expect(parTestId('essai7-priorite')).toBeNull();
    expect(parTestId('essai7-reserve')).toBeNull();
    expect(ordreDe('subscriber-space-reservation')).toBe(0);
    expect(ordreDe('subscriber-space-header')).toBe(0);
  });

  test('son compteur de seances reste affiche', () => {
    expect(parTestId('subscriber-space-sessions').textContent)
      .toContain('Séances restantes');
  });
});

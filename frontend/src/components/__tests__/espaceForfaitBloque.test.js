/**
 * V449 — UNE LISTE VIDE DOIT DIRE POURQUOI ELLE EST VIDE.
 *
 * LE DEFAUT, PAYE EN PRODUCTION LE 02/09/2026. Une abonnee dont le forfait
 * avait expire ouvrait son espace et lisait « Aucun cours disponible pour le
 * moment ». C'est la phrase d'un PLANNING VIDE. Elle en a conclu qu'il n'y
 * avait pas de cours ce soir-la — le coach aussi, qui a cherche une panne de
 * publication pendant que la vraie raison, l'expiration de son forfait, etait
 * ecrite dans la reponse du serveur et jamais affichee.
 *
 * Le serveur envoie DEJA `forfait_bloque` et `forfait_message` exactement pour
 * ca (V393, `upcoming_courses` dans server.py) : il vide la liste ET dit
 * pourquoi. L'ecran ignorait les deux champs.
 *
 * CE BANC MONTE VRAIMENT LE COMPOSANT. Une lecture de source ne prouverait pas
 * quelle phrase est rendue ; ici on lit le DOM.
 *
 * LES DEUX SENS SONT TESTES, et c'est le point : afficher le motif quand il
 * existe ne vaut rien si on l'invente quand il n'existe pas. Un planning
 * reellement vide doit garder SA phrase — sans quoi on aurait remplace un
 * message trompeur par un autre.
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

const CODE = 'ESPACE-FORFAIT-BLOQUE';
const MOTIF = 'Ton abonnement a expiré le 20.08.2026. Contacte le coach pour le renouveler.';

// Le forfait de l'incident : des seances RESTANTES au compteur, et pourtant
// bloque. C'est la combinaison qui rendait la liste vide incomprehensible —
// « il me reste 5 seances, pourquoi aucun cours ? ».
function espace({ bloque, message, cours = [] }) {
  return {
    subscriber: { name: 'Ana Dupont', code: CODE, whatsapp: '+41760000000' },
    subscription: {
      id: 'sub-1', code: CODE, offer_name: 'PULSE x10 cours',
      total_sessions: 7, remaining_sessions: 5, used_sessions: 2,
    },
    coach: { name: 'Afroboost' },
    upcoming_courses: cours,
    reservations: [],
    forfait_bloque: bloque,
    forfait_message: message,
  };
}

let conteneur;
let racine;

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

beforeEach(() => {
  window.history.replaceState({}, '', `/espace/${CODE}`);
  jest.clearAllMocks();
  window.localStorage.setItem('afroboost_espace_token', JSON.stringify({
    token: 'jeton-de-banc', code: CODE, slug: '',
    expires_at: new Date(Date.now() + 30 * 86400000).toISOString(),
  }));
});

afterEach(async () => {
  if (racine) await act(async () => racine.unmount());
  if (conteneur && conteneur.parentNode) conteneur.remove();
});

// ==========================================================================
describe('forfait bloque : la liste vide porte le motif du serveur', () => {
  beforeEach(async () => {
    await monter(espace({ bloque: true, message: MOTIF }));
  });

  test('le motif exact du serveur est rendu', () => {
    const el = parTestId('forfait-bloque-message');
    expect(el).not.toBeNull();
    expect(el.textContent).toContain('expiré le 20.08.2026');
  });

  test('la phrase du planning vide a DISPARU', () => {
    // C'est elle qui mentait. Sa presence ici serait le bug lui-meme.
    expect(conteneur.textContent).not.toContain('Aucun cours disponible pour le moment');
  });

  test('le motif reste lisible meme si le serveur ne fournit pas de phrase', async () => {
    // `forfait_bloque` sans `forfait_message` ne doit pas retomber sur la
    // phrase trompeuse : on prefere un repli generique mais exact.
    if (racine) await act(async () => racine.unmount());
    conteneur.remove();
    await monter(espace({ bloque: true, message: '' }));
    const el = parTestId('forfait-bloque-message');
    expect(el).not.toBeNull();
    expect(el.textContent).toContain('Contacte le coach');
    expect(conteneur.textContent).not.toContain('Aucun cours disponible pour le moment');
  });
});

// ==========================================================================
describe('forfait valide : rien ne change', () => {
  test('un planning reellement vide garde SA phrase', async () => {
    await monter(espace({ bloque: false, message: '' }));
    expect(parTestId('forfait-bloque-message')).toBeNull();
    expect(conteneur.textContent).toContain('Aucun cours disponible pour le moment');
  });

  test('des creneaux disponibles n affichent aucun motif de blocage', async () => {
    const demain = new Date(Date.now() + 36 * 3600 * 1000).toISOString();
    await monter(espace({
      bloque: false, message: '',
      cours: [{ course_id: 'c-42', name: 'Afroboost Silent', datetime: demain,
                date: demain.slice(0, 10), time: '18:30' }],
    }));
    expect(parTestId('forfait-bloque-message')).toBeNull();
    expect(conteneur.textContent).not.toContain('Aucun cours disponible pour le moment');
  });
});

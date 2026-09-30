/**
 * V561 — DASHBOARD COURT : une fonction = un seul point d'entrée (le menu rapide).
 * V564 — « Réserver une séance » est OUVERTE EN LIGNE par défaut ; « Ma progression »
 * remplace « Réserver » dans le menu et s'ouvre dans une fenêtre.
 *
 * Banc DOM réel (jsdom) : au chargement, seuls Bienvenue, le menu rapide, « Ma
 * progression » (une carte) et les prochaines séances. Réserver, Mon QR,
 * Recharger et Créateur s'ouvrent HORS du dashboard ; Inviter et Partenaire
 * mènent aux parcours existants. Aucun réseau (axios mouchard).
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
jest.mock('../SubscriberCockpit', () => () => <div data-testid="cockpit-integre" />);
jest.mock('../InvitationTemoignage', () => ({ __esModule: true, default: () => null, enRepos: () => false }));
jest.mock('../Publications', () => ({ PublishModal: () => null }));
jest.mock('qrcode.react', () => ({ QRCodeSVG: (p) => <svg data-testid="qr-svg" data-value={p.value} /> }));
jest.mock('../ui/dialog', () => ({
  Dialog: ({ open, children }) => (open ? <div data-testid="qr-fenetre">{children}</div> : null),
  DialogContent: ({ children }) => children,
  DialogTitle: ({ children }) => children,
}));

const CODE = 'AFR-2287CA';
const J = (h) => new Date(Date.now() + h * 3600 * 1000).toISOString();

function espace(extra) {
  return Object.assign({
    subscriber: { name: 'Bassi Dupont', code: CODE, whatsapp: '+41760000000', email: 'bassi@exemple.test' },
    subscription: { id: 'sub-1', code: CODE, offer_name: 'Pulse X10', total_sessions: 47, remaining_sessions: 31, used_sessions: 16 },
    coach: { name: 'Afroboost' },
    upcoming_courses: [
      { course_id: 'c-42', name: 'Afroboost Pulse', datetime: J(36), date: J(36).slice(0, 10), time: '18:45' },
      { course_id: 'c-43', name: 'Cours à l’unité', datetime: J(132), date: J(132).slice(0, 10), time: '18:30', location: 'Chem. des Valangines 97' },
    ],
    reservations: [
      { id: 'r-1', courseId: 'c-42', datetime: J(30), courseName: 'Cours à l’unité', locationName: 'Neuchâtel' },
      { id: 'r-2', courseId: 'c-42', datetime: J(60), courseName: 'Afroboost Pulse' },
      { id: 'r-3', courseId: 'c-42', datetime: J(90), courseName: 'Afroboost Silent' },
    ],
    recharge: { eligible: true, offres: [{ offer_id: 'o-10', offer_name: 'Pulse X10', seances: 10, duree_mois: 2, prix: 150, devise: 'CHF', eligible: true }] },
  }, extra || {});
}

let conteneur, racine;
beforeEach(() => {
  window.history.replaceState({}, '', `/espace/${CODE}`);
  jest.clearAllMocks();
  window.localStorage.setItem('afroboost_espace_token', JSON.stringify({
    token: 'jeton-de-banc', code: CODE, slug: '', expires_at: new Date(Date.now() + 30 * 86400000).toISOString(),
  }));
  window.localStorage.setItem('afroboost_parrainage', JSON.stringify({ enabled: true, courses: [], ts: Date.now() }));
});
afterEach(async () => {
  if (racine) await act(async () => racine.unmount());
  racine = null;
  if (conteneur) conteneur.remove();
  window.localStorage.clear();
});

async function monter(reponse, createur) {
  axios.get.mockImplementation((url) => {
    if (String(url).includes('/api/createur/me')) return Promise.resolve({ data: createur || { statut: 'none', est_partenaire: false } });
    return Promise.resolve({ data: reponse });
  });
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  await act(async () => { racine = createRoot(conteneur); racine.render(<SubscriberSpace accessCode={CODE} />); });
  await act(async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); });
}
const par = (id) => document.querySelector(`[data-testid="${id}"]`);
const cliquer = async (id) => { await act(async () => { par(id).click(); }); await act(async () => { for (let i = 0; i < 6; i += 1) await Promise.resolve(); }); };

describe('V564 — dashboard : réservation en ligne, progression dans le menu', () => {
  test('au chargement : ni gros QR, ni Parrainage, ni Créateur, ni Recharger, ni carte 31 / 47, ni guide, aucune fenêtre', async () => {
    await monter(espace());
    ['subscriber-space-qr', 'carte-parrainage', 'carte-createur', 'subscriber-space-recharge', 'recharge-toggle',
      'subscriber-space-sessions', 'progression-reserver', 'subscriber-space-guide', 'parrainage-drawer', 'qr-fenetre']
      .forEach((id) => expect(par(id)).toBeNull());
    expect(par('subscriber-space-header')).not.toBeNull();
    expect(par('menu-rapide')).not.toBeNull();
    expect(document.body.textContent).not.toContain('Séances restantes');
  });

  test('menu : « Ma progression » en premier, « Réserver » absent', async () => {
    await monter(espace());
    const ids = Array.from(document.querySelectorAll('[data-testid="menu-rapide"] button')).map((b) => b.getAttribute('data-testid'));
    expect(ids[0]).toBe('menu-rapide-progression');
    expect(par('menu-rapide-progression').textContent).toBe('Ma progression');
    expect(ids).not.toContain('menu-rapide-reserver');
    ['menu-rapide-qr', 'menu-rapide-inviter', 'menu-rapide-createur', 'menu-rapide-recharger', 'menu-rapide-partenaire']
      .forEach((id) => expect(ids).toContain(id));
  });

  test('« Réserver une séance » visible d’emblée, EN LIGNE : dates, carte de la séance, Réserver', async () => {
    await monter(espace());
    const resa = par('subscriber-space-reservation');
    expect(resa.getAttribute('data-mode')).toBe('inline');
    expect(par('reservation-titre').textContent).toBe('Réserver une séance');
    expect(par('seance-date-0')).not.toBeNull();
    expect(par('seance-date-1')).not.toBeNull();
    expect(par('reserve-c-42')).not.toBeNull();
    // pas une fenêtre : ni fond, ni X, ni verrou de défilement
    expect(resa.closest('[data-testid="parrainage-drawer-fond"]')).toBeNull();
    expect(resa.closest('[role="dialog"]')).toBeNull();
    expect(resa.querySelector('[data-testid="drawer-fermer"]')).toBeNull();
    expect(document.body.style.overflow).not.toBe('hidden');
  });

  test('choisir une date → la carte montre CETTE séance', async () => {
    await monter(espace());
    expect(par('subscriber-space-reservation').textContent).toContain('Afroboost Pulse');
    await cliquer('seance-date-1');
    expect(par('seance-date-1').getAttribute('aria-pressed')).toBe('true');
    expect(par('reserve-c-43')).not.toBeNull();
    expect(par('reserve-c-42')).toBeNull();
    expect(par('subscriber-space-reservation').textContent).toContain('Cours à l’unité');
  });

  test('« Réserver » envoie la réservation de la séance choisie, comme avant', async () => {
    await monter(espace());
    axios.post.mockResolvedValue({ data: { success: true, reservation: { id: 'r-9' } } });
    await cliquer('reserve-c-42');
    const appel = axios.post.mock.calls.find((c) => /reserv/i.test(String(c[0])));
    expect(appel).toBeTruthy();
    expect(String(appel[0]) + JSON.stringify(appel[1])).toContain('c-42'); // le cours voyage dans l'URL
  });

  test('UN seul calendrier : une seule section de réservation, une seule grille de dates', async () => {
    await monter(espace());
    expect(document.querySelectorAll('[data-testid="subscriber-space-reservation"]')).toHaveLength(1);
    expect(document.querySelectorAll('[data-testid="seance-dates"]')).toHaveLength(1);
    expect(document.querySelectorAll('[data-testid="seance-date-0"]')).toHaveLength(1);
  });

  test('mobile : les dates passent à la ligne (jamais de défilement horizontal), cibles de 48 px', async () => {
    await monter(espace());
    expect(par('seance-dates').style.gridTemplateColumns).toBe('repeat(auto-fill, minmax(88px, 1fr))');
    expect(par('seance-date-0').style.minHeight).toBe('48px');
    expect(['0', '0px']).toContain(par('seance-date-0').style.minWidth);
  });

  test('« Ma progression » ouvre la carte existante (31 / 47, barre, détail) dans une fenêtre', async () => {
    await monter(espace());
    await cliquer('menu-rapide-progression');
    expect(par('parrainage-drawer').getAttribute('data-outil')).toBe('progression');
    const carte = par('subscriber-space-sessions');
    expect(carte.textContent).toContain('Ma progression');
    expect(carte.textContent).toContain('31');
    expect(carte.textContent).toContain('/ 47');
    expect(carte.querySelector('[data-testid="cockpit-integre"]')).not.toBeNull();
    expect(document.querySelectorAll('[data-testid="cockpit-integre"]')).toHaveLength(1);
    expect(par('progression-reserver')).toBeNull();
    await cliquer('drawer-fermer');
    expect(par('subscriber-space-sessions')).toBeNull();
    expect(par('subscriber-space-reservation')).not.toBeNull(); // la réservation n'a pas bougé
  });
});

describe('V561 — dashboard court (menu, fenêtres hors réservation)', () => {
  test('libellés selon le statut SERVEUR : créateur approuvé, partenaire', async () => {
    await monter(espace(), { statut: 'approved', est_partenaire: true, dashboard: { kpis: {} } });
    expect(par('menu-rapide-createur').textContent).toBe('Créateur');
    expect(par('menu-rapide-partenaire').textContent).toBe('Partenaire');
  });

  test('prochaines séances : visibles, 2 au plus, puis « Voir toutes mes séances »', async () => {
    await monter(espace());
    const bloc = par('subscriber-space-upcoming');
    expect(bloc).not.toBeNull();
    expect(bloc.querySelectorAll('li')).toHaveLength(2);
    await cliquer('voir-toutes-seances');
    expect(par('subscriber-space-upcoming').querySelectorAll('li')).toHaveLength(3);
  });

  test('Mon QR ouvre la fenêtre QR (QR + code + Copier) ; fermée, elle ne prend aucune place', async () => {
    await monter(espace());
    expect(par('qr-fenetre')).toBeNull();
    await cliquer('menu-rapide-qr');
    expect(par('qr-fenetre')).not.toBeNull();
    expect(par('qr-code-membre').textContent).toBe(CODE);
    expect(par('qr-copier')).not.toBeNull();
  });

  test('Recharger ouvre les VRAIES offres + le renouvellement, dans une fenêtre', async () => {
    await monter(espace({ stripe_amount: 150 }));
    await cliquer('menu-rapide-recharger');
    expect(par('parrainage-drawer').getAttribute('data-outil')).toBe('recharger');
    expect(par('recharge-offre-o-10').textContent).toContain('Pulse X10');
    expect(par('renew-subscription-btn')).not.toBeNull();
    expect(par('recharge-toggle')).toBeNull();
  });

  test('Créateur ouvre le bon parcours (demande pour un non-créateur)', async () => {
    await monter(espace());
    await cliquer('menu-rapide-createur');
    expect(par('parrainage-drawer').getAttribute('data-outil')).toBe('createur');
    expect(par('devenir-createur')).not.toBeNull();
  });
});

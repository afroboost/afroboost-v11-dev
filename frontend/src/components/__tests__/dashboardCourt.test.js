/**
 * V561 — DASHBOARD COURT : une fonction = un seul point d'entrée (le menu rapide).
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
    upcoming_courses: [{ course_id: 'c-42', name: 'Afroboost Pulse', datetime: J(36), date: J(36).slice(0, 10), time: '18:45' }],
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

describe('V561 — dashboard court', () => {
  test('au chargement : ni gros QR, ni Parrainage, ni Créateur, ni Recharger, ni calendrier, ni guide', async () => {
    await monter(espace());
    ['subscriber-space-qr', 'carte-parrainage', 'carte-createur', 'subscriber-space-recharge', 'recharge-toggle',
      'subscriber-space-reservation', 'subscriber-space-guide', 'parrainage-drawer', 'qr-fenetre']
      .forEach((id) => expect(par(id)).toBeNull());
    expect(par('subscriber-space-header')).not.toBeNull();
    expect(par('menu-rapide')).not.toBeNull();
  });

  test('menu rapide = navigation principale : Réserver · Mon QR · Créateur · Recharger · Partenaire (un seul point d’entrée chacun)', async () => {
    await monter(espace());
    const ids = Array.from(document.querySelectorAll('[data-testid="menu-rapide"] button')).map((b) => b.getAttribute('data-testid'));
    ['menu-rapide-reserver', 'menu-rapide-qr', 'menu-rapide-createur', 'menu-rapide-recharger', 'menu-rapide-partenaire']
      .forEach((id) => expect(ids).toContain(id));
    expect(ids).toContain('menu-rapide-inviter');           // Invitation + Parrainage = « Inviter »
    expect(ids).not.toContain('menu-rapide-parrainage');
    expect(ids).not.toContain('menu-rapide-invitation');
    expect(par('menu-rapide-inviter').textContent).toBe('Inviter');
    expect(par('menu-rapide-createur').textContent).toBe('Devenir créateur');
    expect(par('menu-rapide-partenaire').textContent).toBe('Devenir partenaire');
  });

  test('libellés selon le statut SERVEUR : créateur approuvé, partenaire', async () => {
    await monter(espace(), { statut: 'approved', est_partenaire: true, dashboard: { kpis: {} } });
    expect(par('menu-rapide-createur').textContent).toBe('Créateur');
    expect(par('menu-rapide-partenaire').textContent).toBe('Partenaire');
  });

  test('Ma progression = UNE carte (titre, 31 / 47, barre, « Réserver », détail intégré)', async () => {
    await monter(espace());
    const carte = par('subscriber-space-sessions');
    expect(carte.textContent).toContain('Ma progression');
    expect(carte.textContent).toContain('31');
    expect(carte.textContent).toContain('/ 47');
    expect(carte.querySelector('[data-testid="progression-reserver"]')).not.toBeNull();
    expect(carte.querySelector('[data-testid="cockpit-integre"]')).not.toBeNull();
    expect(document.querySelectorAll('[data-testid="cockpit-integre"]')).toHaveLength(1);
  });

  test('prochaines séances : visibles, 2 au plus, puis « Voir toutes mes séances »', async () => {
    await monter(espace());
    const bloc = par('subscriber-space-upcoming');
    expect(bloc).not.toBeNull();
    expect(bloc.querySelectorAll('li')).toHaveLength(2);
    await cliquer('voir-toutes-seances');
    expect(par('subscriber-space-upcoming').querySelectorAll('li')).toHaveLength(3);
  });

  test('Réserver (menu ET progression) ouvre le sélecteur de séance dans une fenêtre', async () => {
    await monter(espace());
    await cliquer('menu-rapide-reserver');
    expect(par('parrainage-drawer').getAttribute('data-outil')).toBe('reserver');
    expect(par('subscriber-space-reservation')).not.toBeNull();
    await cliquer('drawer-fermer');
    expect(par('subscriber-space-reservation')).toBeNull();
    await cliquer('progression-reserver');
    expect(par('subscriber-space-reservation')).not.toBeNull();
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

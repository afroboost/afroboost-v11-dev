/**
 * V565 — ESPACE ABONNÉ : Recharger (offres réelles, Renouveler / Acheter, checkout
 * existant) + Affiche Événement du coach en ligne au-dessus de la réservation.
 * Reprend le harnais du banc V561 — DASHBOARD COURT : une fonction = un seul point d'entrée (le menu rapide).
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


const OFFRES = [
  { offer_id: 'o-fond', offer_name: 'Fondateurs', eligible: true, action: 'acheter', actuelle: false },
  { offer_id: 'o-sais', offer_name: 'Saison hiver — 8 mois', eligible: true, action: 'acheter', actuelle: false },
  { offer_id: 'o-mens', offer_name: 'Mensuel Liberté', eligible: true, action: 'renouveler', actuelle: true },
  { offer_id: 'o-1', offer_name: 'Cours à l’unité', eligible: true, action: 'acheter', actuelle: false },
  { offer_id: 'o-m', offer_name: 'Membres', eligible: false, action: 'acheter', actuelle: false,
    message: 'Il te reste des séances sur ton pack actuel. Termine-les avant de le recharger.' },
  { offer_id: 'o-s2', offer_name: 'Saison hiver — 2 paiements', eligible: true, action: 'acheter', actuelle: false,
    paiement_integral: true, billing_mode: 'saison_2x', prix: 299 },
];
// Les offres telles que `GET /offers` les donne à la vitrine (catalogue V566).
const CATALOGUE = [
  { id: 'o-fond', name: 'Fondateurs', price: 59, billing_mode: 'mensuel_auto', stock: 50, places_restantes: 50, pack_sessions: 8, thumbnail: 'https://res.cloudinary.com/x/fond.jpg', position: 1 },
  { id: 'o-sais', name: 'Saison hiver — 8 mois', price: 549, duree_mois: 8, pack_sessions: 64, thumbnail: 'https://res.cloudinary.com/x/saison.jpg', position: 2 },
  { id: 'o-s2', name: 'Saison hiver — 2 paiements', price: 299, billing_mode: 'saison_2x', pack_sessions: 8, position: 3 },
  { id: 'o-mens', name: 'Mensuel Liberté', price: 89, billing_mode: 'mensuel_auto', pack_sessions: 8, position: 4 },
  { id: 'o-1', name: 'Cours à l’unité', price: 30, position: 5 },
  { id: 'o-m', name: 'Membres', price: 150, pack_sessions: 10, position: 6 },
];
const AFFICHE = { media_url: 'https://res.cloudinary.com/x/affiche.jpg', reserve_label: 'Je réserve', cle: 'k1' };
const RECH = { eligible: false, offres: OFFRES, catalogue: CATALOGUE };
const ouvrirRecharger = async () => { await cliquer('menu-rapide-recharger'); };
const ligne = (id) => document.querySelector(`[data-testid="ligne-offre-${id}"]`);

describe('V566 — Recharger = le sélecteur d’offres de la vitrine', () => {
  beforeEach(() => { try { window.sessionStorage.clear(); } catch (e) { /* */ } });

  test('Recharger ouvre LE panneau « Toutes les offres » du site, titré « Recharger mes séances »', async () => {
    await monter(espace({ recharge: RECH }));
    await ouvrirRecharger();
    const panneau = par('toutes-les-offres');
    expect(panneau).not.toBeNull();
    expect(panneau.getAttribute('aria-label')).toBe('Recharger mes séances');
    expect(par('recharge-offres')).toBeNull();            // l'ancienne liste maison n'existe plus
    expect(document.querySelector('[data-testid^="recharge-cta-"]')).toBeNull();
    expect(par('parrainage-drawer')).toBeNull();
  });

  test('mêmes groupes, badges, images, économies et prix que la vitrine', async () => {
    await monter(espace({ recharge: RECH }));
    await ouvrirRecharger();
    ['groupe-lancement', 'groupe-saison', 'groupe-mensuel', 'groupe-unite'].forEach((g) => expect(par(g)).not.toBeNull());
    expect(par('groupe-lancement').textContent).toContain('Offre de lancement');
    expect(par('groupe-mensuel').textContent).toContain('Chaque mois, sans engagement');
    expect(ligne('o-fond').textContent).toContain('Offre lancement');
    expect(ligne('o-mens').textContent).toContain('Le plus flexible');
    expect(ligne('o-fond').querySelector('img').getAttribute('src')).toBe('https://res.cloudinary.com/x/fond.jpg');
    expect(ligne('o-sais').textContent).toContain('Économie');
    expect(ligne('o-mens').textContent).toContain('89');
    // ordre de la vitrine : lancement, saison, mensuel, unité
    const ordre = Array.from(document.querySelectorAll('[data-testid^="ligne-offre-"]')).map((b) => b.getAttribute('data-testid'));
    expect(ordre.indexOf('ligne-offre-o-fond')).toBeLessThan(ordre.indexOf('ligne-offre-o-sais'));
    expect(ordre.indexOf('ligne-offre-o-sais')).toBeLessThan(ordre.indexOf('ligne-offre-o-mens'));
    expect(ordre.indexOf('ligne-offre-o-mens')).toBeLessThan(ordre.indexOf('ligne-offre-o-1'));
  });

  test('offre détenue → « Ton offre » discret ; refus → la vraie raison, discrètement', async () => {
    await monter(espace({ recharge: RECH }));
    await ouvrirRecharger();
    expect(par('note-offre-o-mens').textContent).toBe('Ton offre');
    expect(par('note-offre-o-m').textContent).toContain('Termine-les');
    expect(par('note-offre-o-1')).toBeNull();
  });

  test('clic sur une ligne → la fiche du site → « Choisir cette formule » → checkout EXISTANT', async () => {
    const loc = window.location;
    delete window.location; window.location = { ...loc, href: '', origin: 'https://afroboost.com', pathname: loc.pathname };
    axios.post.mockResolvedValue({ data: { url: 'https://checkout.stripe.com/x' } });
    await monter(espace({ recharge: RECH }));
    await ouvrirRecharger();
    await act(async () => { ligne('o-1').click(); });
    expect(par('fiche-offre')).not.toBeNull();
    await cliquer('fiche-cta');
    const [url, corps] = axios.post.mock.calls[0];
    expect(String(url)).toMatch(/\/create-checkout-session$/);
    expect(corps.offerId).toBe('o-1');
    expect(window.location.href).toBe('https://checkout.stripe.com/x');
    window.location = loc;
  });

  test('offre à choix de paiement → le choix existant (ChoixModePaiement), jamais un paiement direct', async () => {
    await monter(espace({ recharge: RECH }));
    await ouvrirRecharger();
    await act(async () => { ligne('o-s2').click(); });
    await cliquer('fiche-cta');
    expect(par('recharge-choix')).not.toBeNull();
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('offre refusée : la fiche ne lance rien, la raison est dite', async () => {
    await monter(espace({ recharge: RECH }));
    await ouvrirRecharger();
    await act(async () => { ligne('o-m').click(); });
    await cliquer('fiche-cta');
    expect(par('recharge-choix-refus').textContent).toContain('Termine-les');
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('sans catalogue : repli historique (tiroir, motif), rien d’inventé', async () => {
    await monter(espace({ recharge: { eligible: false, message: 'Cette recharge est réservée aux membres.' } }));
    await ouvrirRecharger();
    expect(par('toutes-les-offres')).toBeNull();
    expect(par('recharge-motif').textContent).toContain('réservée aux membres');
  });
});

describe('V565 — Affiche Événement dans l’espace', () => {
  beforeEach(() => { try { window.sessionStorage.clear(); } catch (e) { /* */ } });

  test('désactivée (evenement absent) → rien, et la réservation suit directement le menu', async () => {
    await monter(espace());
    expect(par('espace-affiche-evenement')).toBeNull();
    expect(par('subscriber-space-reservation')).not.toBeNull();
  });

  test('activée + image → image AVANT « Réserver une séance », boutons du coach', async () => {
    await monter(espace({ evenement: AFFICHE }));
    const affiche = par('espace-affiche-evenement');
    expect(par('espace-affiche-image').getAttribute('src')).toBe(AFFICHE.media_url);
    const resa = par('subscriber-space-reservation');
    expect(affiche.compareDocumentPosition(resa) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(par('espace-affiche-reserver').textContent).toContain('Je réserve');       // libellé du coach
    expect(par('espace-affiche-offres').textContent).toContain('Nos offres');         // jamais renseigné → défaut
    expect(affiche.closest('[data-testid="parrainage-drawer-fond"]')).toBeNull();      // en ligne, pas une fenêtre
  });

  test('libellé vidé par le coach → bouton masqué (règle de la vitrine)', async () => {
    await monter(espace({ evenement: { ...AFFICHE, offers_label: '' } }));
    expect(par('espace-affiche-offres')).toBeNull();
    expect(par('espace-affiche-reserver')).not.toBeNull();
  });

  test('vidéo YouTube → lecteur intégré (même URL que la vitrine)', async () => {
    await monter(espace({ evenement: { media_url: 'https://youtu.be/abc123', cle: 'k2' } }));
    expect(par('espace-affiche-video').getAttribute('src')).toBe('https://www.youtube.com/embed/abc123?autoplay=1&mute=1');
  });

  test('« Nos offres » ouvre le catalogue du coach (Recharger)', async () => {
    await monter(espace({ evenement: AFFICHE, recharge: RECH }));
    await cliquer('espace-affiche-offres');
    expect(par('toutes-les-offres').getAttribute('aria-label')).toBe('Recharger mes séances'); // V566
  });

  test('X → masquée ici seulement (aucun appel serveur) ; une NOUVELLE affiche réapparaît', async () => {
    await monter(espace({ evenement: AFFICHE }));
    const appels = axios.post.mock.calls.length + axios.put.mock.calls.length;
    await cliquer('espace-affiche-fermer');
    expect(par('espace-affiche-evenement')).toBeNull();
    expect(axios.post.mock.calls.length + axios.put.mock.calls.length).toBe(appels);
    await act(async () => racine.unmount()); racine = null; conteneur.remove();
    await monter(espace({ evenement: AFFICHE }));
    expect(par('espace-affiche-evenement')).toBeNull();                                // même affiche : reste fermée
    await act(async () => racine.unmount()); racine = null; conteneur.remove();
    await monter(espace({ evenement: { ...AFFICHE, media_url: 'https://res.cloudinary.com/x/nouvelle.jpg', cle: 'k9' } }));
    expect(par('espace-affiche-evenement')).not.toBeNull();                            // nouvelle affiche : visible
  });

  test('mobile : carte et média à 100 % de largeur, jamais de débordement', async () => {
    await monter(espace({ evenement: AFFICHE }));
    expect(par('espace-affiche-evenement').style.maxWidth).toBe('100%');
    expect(par('espace-affiche-image').style.width).toBe('100%');
    expect(par('espace-affiche-boutons').style.flexWrap).toBe('wrap');
  });

  test('la réservation en ligne reste fonctionnelle sous l’affiche', async () => {
    await monter(espace({ evenement: AFFICHE }));
    expect(par('reserve-c-42')).not.toBeNull();
    await cliquer('espace-affiche-reserver');                                          // descend, n'ouvre rien
    expect(par('parrainage-drawer')).toBeNull();
  });
});

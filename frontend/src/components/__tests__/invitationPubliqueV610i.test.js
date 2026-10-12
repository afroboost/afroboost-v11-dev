/**
 * V610i — page publique de l'invitation : parcours court, lecteur ADAPTATIF, réservation
 * directe vers Stripe, retour confirmé par le WEBHOOK, boule de neige après réservation.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn(), create: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } }));
// eslint-disable-next-line import/first
import InvitationPublique, { libelleRatio, retourPaiement, ConfirmationReservation, VideoAdaptative } from '../InvitationPublique';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let conteneur = null; let racine = null;
function rendre(el) { conteneur = document.createElement('div'); document.body.appendChild(conteneur); racine = createRoot(conteneur); racine.render(el); }
afterEach(() => { if (racine) act(() => racine.unmount()); if (conteneur) conteneur.remove(); racine = null; conteneur = null; delete global.fetch; window.localStorage.clear(); window.history.replaceState({}, '', '/'); });
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
async function attendre(fn) { let e; for (let i = 0; i < 60; i += 1) { try { fn(); return; } catch (x) { e = x; } await act(async () => { await new Promise((r) => setTimeout(r, 20)); }); } throw e; }
const json = (corps, ok = true, status = 200) => Promise.resolve({ ok, status, json: () => Promise.resolve(corps) });

const SILENT = {
  type: 'event_paid', title: 'AFROBOOST SILENT — ÉDITION SPÉCIALE', subtitle: '1 heure de cardio-danse afro au casque.',
  date_label: 'mercredi 28 octobre', time_label: '18:45', lieu: 'Chemin des Valangines 97, 2000 Neuchâtel',
  inviter_display: { prenom: 'Bassi' }, video_url: '/api/files/v1/silent.mp4', image_url: '/api/files/i1/mini.jpg',
  description: 'Casque fourni. Tous niveaux.', gratuit_membres: true, audio_partage_url: '/api/files/a1/afro.mp3',
  cible: '/?offre=OFF&inv=T', reservation_directe: { offer_id: 'OFF-1' },
  prix_actif: { prix: 25, palier: 'early_bird', libelle: 'Prévente',
    paliers: [{ palier: 'early_bird', libelle: 'Prévente', prix: 25, actif: true, jusqu_a: '2026-10-21T16:45:00+00:00' },
      { palier: 'standard', libelle: 'Standard', prix: 30, actif: false, jusqu_a: '2026-10-27T17:45:00+00:00' },
      { palier: 'last_minute', libelle: 'Dernière minute', prix: 40, actif: false }],
    prochain: { palier: 'standard', prix: 30, a_partir_de: '2026-10-21T16:45:00+00:00' } },
};

describe('V610i — lecteur vidéo adaptatif', () => {
  test('ratio réel : 9:16, 16:9, 1:1, autre', () => {
    expect(libelleRatio(1080, 1920)).toBe('9:16');
    expect(libelleRatio(1920, 1080)).toBe('16:9');
    expect(libelleRatio(1080, 1080)).toBe('1:1');
    expect(libelleRatio(608, 1080)).toBe('9:16');
    expect(libelleRatio(1000, 700)).toBe('1000:700');
  });
  test.each([[1080, 1920, '9:16'], [1920, 1080, '16:9'], [1080, 1080, '1:1']])('vidéo %ix%i -> cadre %s, affiche dans le MÊME cadre, rien de forcé', async (l, h, attendu) => {
    await act(async () => { rendre(<VideoAdaptative src="/v.mp4" poster="/p.jpg" titre="T" />); });
    const v = q('inv-pub-video');
    Object.defineProperty(v, 'videoWidth', { configurable: true, get: () => l });
    Object.defineProperty(v, 'videoHeight', { configurable: true, get: () => h });
    await act(async () => { v.dispatchEvent(new Event('loadedmetadata')); });
    const cadre = q('inv-pub-video-cadre');
    expect(cadre.getAttribute('data-ratio')).toBe(attendu);
    expect(cadre.getAttribute('data-source-ratio')).toBe('video');
    expect(cadre.style.aspectRatio.replace(/\s/g, '')).toBe(`${l}/${h}`);
    expect(v.getAttribute('poster')).toBe('/p.jpg');                 // l'affiche occupe le même cadre que la vidéo
    expect(v.style.width).toBe('100%'); expect(v.style.height).toBe('100%');
    expect(v.style.objectFit).toBe('contain');                        // jamais de recadrage forcé
    expect(v.autoplay).toBe(false);
    expect(v.getAttribute('controlslist')).toBe('nodownload noremoteplayback');
    expect(v.hasAttribute('controls')).toBe(true);
  });
});

describe('V610i — page courte, réservation directe', () => {
  test('ordre et unicité : date / heure / lieu une fois ; membre compact ; « Lire plus » sans répétition ; aucun audio avant réservation', async () => {
    global.fetch = jest.fn((url) => (String(url).includes('/api/invitation/publique/') ? json(SILENT) : json({})));
    await act(async () => { rendre(<InvitationPublique token="TOKENSILENT12345678" />); });
    await attendre(() => expect(q('inv-pub-titre')).toBeTruthy());
    const texte = document.body.textContent;
    expect(texte.match(/28 octobre/g)).toHaveLength(1);
    expect(texte.match(/18:45/g)).toHaveLength(1);
    expect(texte.match(/Valangines/g)).toHaveLength(1);
    expect(q('inv-pub-membre-compact').textContent).toBe('Membre Afroboost 8 mois ? Réserve gratuitement');
    expect(q('inv-pub-gratuit-membres')).toBeNull();                   // pas de gros bloc sur la page
    expect(q('afroboosteur-titre')).toBeNull();                        // l'audio d'après réservation n'est pas ici
    expect(q('afroboosteur-audio')).toBeNull();
    expect(q('inv-pub-lire-plus').textContent).toMatch(/Lire plus/);
    expect(texte).not.toMatch(/Détails|Choisir cette formule/);
    await act(async () => { q('inv-pub-lire-plus').click(); });
    const plus = q('inv-pub-lire-plus-contenu').textContent;
    expect(plus).toMatch(/Casque fourni/);
    expect(plus).toMatch(/carte ou TWINT/);
    expect(plus).toMatch(/Prévente 25 CHF jusqu'au 21 octobre à 18h45 · Standard 30 CHF jusqu'au 27 octobre à 18h45 · Dernière minute 40 CHF/);
    expect(q('inv-pub-urgence').textContent).toBe('30 CHF dès le mercredi 21 octobre.');
    expect(q('inv-pub-gratuit-membres').textContent).toMatch(/Ta place est offerte/);
    expect(plus).not.toMatch(/28 octobre|18:45|Valangines/);           // rien de ce qui est déjà affiché
    // jeton mémorisé : le membre qui file vers son espace garde son inviteur direct
    expect(JSON.parse(window.localStorage.getItem('af_invitation')).t).toBe('TOKENSILENT12345678');
  });

  test('« Je réserve ma place » -> checkout DIRECT (offre, quantité 1, retour /i/ demandé, jeton joint) -> Stripe', async () => {
    const appels = [];
    global.fetch = jest.fn((url, opt) => {
      appels.push([String(url), opt]);
      if (String(url).includes('/api/invitation/publique/')) return json(SILENT);
      if (String(url).includes('/api/create-checkout-session')) return json({ url: 'https://checkout.stripe.com/c/pay/cs_test_abc', sessionId: 'cs_test_abc' });
      return json({});
    });
    const lieu = window.location;
    delete window.location; window.location = { href: 'https://afroboost.com/i/TOKENSILENT12345678', origin: 'https://afroboost.com', search: '' };
    try {
      await act(async () => { rendre(<InvitationPublique token="TOKENSILENT12345678" />); });
      await attendre(() => expect(q('inv-pub-cta')).toBeTruthy());
      expect(q('inv-pub-cta').textContent).toBe('Je réserve ma place');
      await act(async () => { q('inv-pub-cta').click(); });
      await attendre(() => expect(window.location.href).toBe('https://checkout.stripe.com/c/pay/cs_test_abc'));
      const [, opt] = appels.find(([u]) => u.includes('/api/create-checkout-session'));
      const corps = JSON.parse(opt.body);
      expect(corps).toEqual(expect.objectContaining({ offerId: 'OFF-1', quantity: 1, retourInvitation: true }));
      expect(corps.attribution.invitation).toBe('TOKENSILENT12345678');
      expect(corps.customerEmail).toBeUndefined();                    // aucune fenêtre de coordonnées avant Stripe
      expect(appels.some(([u]) => u.includes('/api/invitation/suivi'))).toBe(true);
    } finally { window.location = lieu; }
  });

  test('refus serveur (ex. événement masqué) : message clair, pas de redirection', async () => {
    global.fetch = jest.fn((url) => {
      if (String(url).includes('/api/invitation/publique/')) return json(SILENT);
      if (String(url).includes('/api/create-checkout-session')) return json({ detail: "Cet événement n'est pas disponible à la réservation pour le moment." }, false, 409);
      return json({});
    });
    await act(async () => { rendre(<InvitationPublique token="TOKENSILENT12345678" />); });
    await attendre(() => expect(q('inv-pub-cta')).toBeTruthy());
    await act(async () => { q('inv-pub-cta').click(); });
    await attendre(() => expect(q('inv-pub-cta-erreur').textContent).toMatch(/pas disponible/));
  });
});

describe('V610i — retour de Stripe : le webhook fait foi', () => {
  test('paramètres de retour posés par le serveur', () => {
    expect(retourPaiement('?paiement=ok&cs=cs_test_ABCDEF123')).toEqual({ ok: true, cs: 'cs_test_ABCDEF123' });
    expect(retourPaiement('?paiement=ok&cs=<script>')).toBeNull();
    expect(retourPaiement('?paiement=annule')).toEqual({ annule: true });
    expect(retourPaiement('?status=success&session_id=cs_x')).toBeNull();
  });

  test('« Confirmation… » tant que la place n\'est pas confirmée, puis « Ta place est réservée » + Deviens Afroboosteur + lien perso', async () => {
    let n = 0;
    global.fetch = jest.fn((url) => {
      const u = String(url);
      if (u.includes('/api/invitation/relais/session/')) {
        n += 1;
        if (n === 1) return json({ detail: 'Introuvable' }, false, 404);                       // webhook pas encore passé
        if (n === 2) return json({ jeton: 'JETONSOPHIE123456789', share_url: 'https://afroboost.com/i/JETONSOPHIE123456789', place_confirmee: false });
        return json({ jeton: 'JETONSOPHIE123456789', share_url: 'https://afroboost.com/i/JETONSOPHIE123456789', place_confirmee: true, titre: 'SILENT' });
      }
      if (u.includes('/api/invitation/publique/')) return json(SILENT);
      return json({});
    });
    await act(async () => { rendre(<ConfirmationReservation cs="cs_test_ABCDEF123" d={SILENT} attente={() => 5} />); });
    expect(q('inv-pub-confirmation-attente').textContent).toBe('Confirmation de ta réservation…');
    expect(q('inv-pub-place-reservee')).toBeNull();
    await attendre(() => expect(q('inv-pub-place-reservee').textContent).toBe('Ta place est réservée'));
    expect(n).toBe(3);
    await attendre(() => expect(q('afroboosteur-titre').textContent).toMatch(/Deviens Afroboosteur/));
    expect(q('afroboosteur-audio').autoplay).toBe(false);
    expect(q('inviter-whatsapp').textContent).toMatch(/Inviter mes amis/);
    expect(document.body.textContent).toMatch(/Copier mon lien/);
  });

  test('pas de boucle infinie : délai dépassé -> message clair (jamais « réservée » sans preuve)', async () => {
    global.fetch = jest.fn(() => json({ detail: 'Introuvable' }, false, 404));
    await act(async () => { rendre(<ConfirmationReservation cs="cs_test_ABCDEF123" d={SILENT} attente={() => 2} essais={4} />); });
    await attendre(() => expect(q('inv-pub-confirmation-delai')).toBeTruthy());
    expect(global.fetch).toHaveBeenCalledTimes(4);
    expect(q('inv-pub-place-reservee')).toBeNull();
  });
});

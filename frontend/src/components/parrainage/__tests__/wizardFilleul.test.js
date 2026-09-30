/**
 * V556 — PARRAINAGE V3 « BOULE DE NEIGE » : le parcours du filleul (/duo/<token>).
 *
 * axios est mocké : aucun réseau. `fetch` (contrôle d'aperçu navigateur) est
 * mocké par test ; absent, le contrôle retombe sur « Aperçu simplifié ».
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import fs from 'fs';
import path from 'path';
import InvitationDuo from '../InvitationDuo';
import {
  verifierApercuNavigateur, messageRefus, MESSAGE_CHAINE_DEFAUT, cleChaine, _resetParrainagePourTest,
} from '../../../utils/parrainage';

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), patch: jest.fn(), delete: jest.fn() },
}));
jest.mock('qrcode.react', () => ({
  QRCodeSVG: (p) => <svg data-testid="qr-svg" data-value={p.value} />,
  QRCodeCanvas: (p) => <canvas data-testid="qr-canvas" data-value={p.value} />,
}));

let conteneur, racine;
const fetchOrigine = global.fetch;
beforeEach(() => {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  jest.clearAllMocks();
  axios.get.mockReset(); axios.post.mockReset(); axios.patch.mockReset();
  window.localStorage.clear();
  _resetParrainagePourTest();
  global.fetch = undefined;
  window.open = jest.fn(() => null);
  delete navigator.share; delete navigator.canShare;
});
afterEach(() => {
  if (racine) act(() => racine.unmount());
  racine = null;
  conteneur.remove();
  global.fetch = fetchOrigine;
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const vider = () => act(async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); });
async function monter(element) {
  await act(async () => { racine = createRoot(conteneur); racine.render(element); });
  await vider();
}
const cliquer = async (id) => { await act(async () => { par(id).click(); }); await vider(); };
// V558 : Offre → Séance → Ta carte (l'enfant naît ici) → Partage.
const allerALaCarte = async () => { await cliquer('wf-continuer'); await cliquer('wf-seance-continuer'); };
const allerAuPartage = async () => { await allerALaCarte(); await cliquer('wf-carte-continuer'); };

const COURSE = { id: 'c1', name: 'Afroboost Dimanche', time: '18:30', locationName: 'Bord du Lac, Auvernier' };
const OCC = '2026-09-27T18:30:00';
const PUB = { status: 'waiting', sponsor_first_name: 'Bassi', course: COURSE, occurrence: OCC, expired: false, version: 1,
  chain_required: true, chain: { exists: false, shared: false } };
const CHILD = (v) => ({
  share_token: 'T1', share_url: `https://afroboost.com/api/share/duo/T1?v=${v}`,
  invite_url: 'https://afroboost.com/duo/T1', card_url: 'https://afroboost.com/api/share/duo/T1/carte.jpg?v=h1',
  display_name: null, message: MESSAGE_CHAINE_DEFAUT, course: COURSE, occurrence: OCC,
});
const PREVIEW_OK = { ok: true, fallback: false, checks: {} };

/** Routeur des POST : /chain, /chain/share, /join. */
function routerPost({ join } = {}) {
  axios.post.mockImplementation((url) => {
    const u = String(url);
    if (u.endsWith('/chain')) return Promise.resolve({ status: 201, data: { child: CHILD(3), edit_key: 'K1', shared: false, preview: PREVIEW_OK } });
    if (u.endsWith('/chain/share')) return Promise.resolve({ data: { shared: true, shared_at: '2026-09-28T10:00:00Z', child: CHILD(4) } });
    if (u.endsWith('/join')) return join ? join() : Promise.resolve({ data: { status: 'friend_registered', tickets: [] } });
    return Promise.reject(new Error(`inattendu ${u}`));
  });
}

describe('V556 — WizardFilleul (parcours boule de neige)', () => {
  test('chain_required:false → ancien formulaire direct, aucun wizard ni POST /chain', async () => {
    axios.get.mockResolvedValue({ data: Object.assign({}, PUB, { chain_required: false }) });
    await monter(<InvitationDuo token="T0" />);
    expect(par('wf-etape-1')).toBeNull();
    expect(par('invitation-form')).not.toBeNull();
    expect(par('invitation-rejoindre').textContent).toContain("M'inscrire et débloquer le duo");
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('serveur ancien (champ absent) → ancien formulaire', async () => {
    const ancien = Object.assign({}, PUB); delete ancien.chain_required; delete ancien.chain;
    axios.get.mockResolvedValue({ data: ancien });
    await monter(<InvitationDuo token="T0" />);
    expect(par('wf-etape-1')).toBeNull();
    expect(par('invitation-form')).not.toBeNull();
  });

  test('étape 1 : textes, séance, pas de formulaire ; Continuer → POST /chain AVANT tout partage', async () => {
    routerPost();
    axios.get.mockResolvedValue({ data: PUB });
    await monter(<InvitationDuo token="T0" />);
    expect(par('wf-etape-1')).not.toBeNull();
    expect(par('carte-invitation-titre').textContent).toBe('Bassi t’invite à découvrir Afroboost'); // V560 : UNE carte
    expect(par('wf-lead').textContent).toContain('Pour débloquer ton essai, invite à ton tour une autre personne.');
    expect(par('wf-regle-essai').textContent).toContain('L’essai gratuit est disponible une seule fois par personne.');
    expect(par('carte-invitation-quand')).not.toBeNull(); // la séance est DANS la carte
    expect(par('invitation-form')).toBeNull();
    expect(conteneur.textContent).not.toContain("M'inscrire et débloquer le duo");
    await cliquer('wf-continuer');
    expect(par('wf-etape-2')).not.toBeNull();          // V558 : l'étape « Séance »
    expect(axios.post).not.toHaveBeenCalled();         // l'enfant n'existe pas avant la séance
    await cliquer('wf-seance-continuer');
    expect(par('wf-etape-carte')).not.toBeNull();
    const appels = axios.post.mock.calls.map((c) => String(c[0]));
    expect(appels).toEqual([expect.stringMatching(/\/pass\/T0\/chain$/)]);
    expect(window.localStorage.getItem(cleChaine('T0'))).toBe('K1');
    expect(par('wf-apercu')).not.toBeNull(); // V560 : la carte unique, rendue en direct
    expect(par('wf-nom')).not.toBeNull();
  });

  test('boutons de partage désactivés pendant la préparation', async () => {
    let resoudre;
    axios.post.mockImplementation(() => new Promise((r) => { resoudre = r; }));
    axios.get.mockResolvedValue({ data: PUB });
    await monter(<InvitationDuo token="T0" />);
    await allerALaCarte();
    expect(par('wf-preparation').textContent).toContain('Préparation de ton invitation…');
    expect(par('wf-whatsapp')).toBeNull(); // rien de cliquable avant l'enfant
    expect(par('wf-carte-continuer')).toBeNull();
    // l'enfant arrive, mais le contrôle navigateur n'a pas encore répondu → toujours désactivé
    const enAttente = [];
    global.fetch = jest.fn(() => new Promise((r) => { enAttente.push(r); }));
    await act(async () => { resoudre({ status: 201, data: { child: CHILD(3), edit_key: 'K1', preview: PREVIEW_OK } }); });
    await vider();
    await cliquer('wf-carte-continuer');
    expect(par('wf-whatsapp').disabled).toBe(true);
    expect(par('wf-copier').disabled).toBe(true);
    expect(par('wf-preparation')).not.toBeNull();
    // le contrôle échoue (404) → repli discret, boutons actifs
    expect(enAttente.length).toBe(2); // carte + page d'aperçu
    await act(async () => { enAttente.forEach((r) => r({ ok: false, status: 404, headers: { get: () => '' } })); });
    await vider();
    expect(par('wf-whatsapp').disabled).toBe(false);
    expect(par('wf-apercu-simplifie')).not.toBeNull();
  });

  test('WhatsApp ouvre le share_url COURANT (synchrone) puis POST /chain/share, puis étape 3 avec le formulaire', async () => {
    routerPost();
    axios.get.mockResolvedValue({ data: PUB });
    await monter(<InvitationDuo token="T0" />);
    await allerAuPartage();
    expect(par('invitation-form')).toBeNull();
    await cliquer('wf-whatsapp');
    expect(window.open).toHaveBeenCalledTimes(1);
    const lien = decodeURIComponent(String(window.open.mock.calls[0][0]));
    expect(lien).toContain(`${MESSAGE_CHAINE_DEFAUT}\nhttps://afroboost.com/api/share/duo/T1?v=3`);
    const share = axios.post.mock.calls.find((c) => String(c[0]).endsWith('/chain/share'));
    expect(share[1]).toEqual({ channel: 'whatsapp' });
    expect(par('wf-etape-3')).not.toBeNull();
    expect(conteneur.textContent).toContain('Invitation envoyée');
    expect(conteneur.textContent).toContain('Termine ton inscription pour réserver ta place.');
    expect(conteneur.textContent).not.toContain('essai gratuit est maintenant débloqué');
    expect(par('invitation-form')).not.toBeNull();
    expect(par('invitation-rejoindre').textContent).toContain("M'inscrire à mon essai gratuit");
    // « Partager encore » : le 2e partage utilise la NOUVELLE share_url (v=4)
    await cliquer('wf-partager-encore');
    expect(par('wf-etape-partage')).not.toBeNull();
    expect(axios.post.mock.calls.filter((c) => String(c[0]).endsWith('/chain')).length).toBe(1);
    await cliquer('wf-whatsapp');
    expect(decodeURIComponent(String(window.open.mock.calls[1][0]))).toContain('/duo/T1?v=4');
  });

  test('échec de POST /chain/share → message + Réessayer, pas d\'étape 3', async () => {
    axios.post.mockImplementation((url) => (String(url).endsWith('/chain')
      ? Promise.resolve({ status: 201, data: { child: CHILD(3), edit_key: 'K1', preview: PREVIEW_OK } })
      : Promise.reject({ response: { status: 500 } })));
    axios.get.mockResolvedValue({ data: PUB });
    await monter(<InvitationDuo token="T0" />);
    await allerAuPartage();
    await cliquer('wf-whatsapp');
    expect(par('wf-etape-3')).toBeNull();
    expect(par('wf-erreur-partage')).not.toBeNull();
    routerPost();
    await cliquer('wf-reessayer-partage');
    expect(par('wf-etape-3')).not.toBeNull();
    expect(window.open).toHaveBeenCalledTimes(1); // réessayer n'ouvre pas une 2e fois WhatsApp
  });

  // UX-P2 : plus de bouton « Mettre à jour ma carte » — le partage force l'enregistrement.
  test('prénom modifié puis WhatsApp tout de suite → PATCH (X-Chain-Key) AVANT le partage, prénom prérempli', async () => {
    routerPost();
    axios.patch.mockResolvedValue({ data: { child: Object.assign(CHILD(5), { display_name: 'Henri' }), preview: PREVIEW_OK } });
    const fen = { location: { href: '' }, close: jest.fn() };
    window.open = jest.fn(() => fen);
    axios.get.mockResolvedValue({ data: PUB });
    await monter(<InvitationDuo token="T0" />);
    await allerALaCarte();
    const input = par('wf-nom');
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(input, 'Henri');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(par('wf-mettre-a-jour')).toBeNull();
    // V558 : « Continuer » vers le partage FORCE l'enregistrement (PATCH avant tout partage).
    await cliquer('wf-carte-continuer');
    const appel = axios.patch.mock.calls[0];
    expect(String(appel[0])).toMatch(/\/pass\/T0\/chain$/);
    expect(appel[1]).toEqual({ display_name: 'Henri', message: MESSAGE_CHAINE_DEFAUT });
    expect(appel[2].headers).toEqual({ 'X-Chain-Key': 'K1' });
    expect(par('wf-whatsapp').disabled).toBe(false);
    await cliquer('wf-whatsapp');
    expect(decodeURIComponent(String(window.open.mock.calls[0][0]))).toContain('/duo/T1?v=5');
    expect(par('invitation-prenom').value).toBe('Henri'); // prérempli par l'étape 2
  });

  test('chain.shared:true → directement l\'étape 3 (vérité serveur), aucun POST', async () => {
    window.localStorage.setItem(cleChaine('T0'), 'K1'); // même appareil que le partage
    axios.get.mockResolvedValue({ data: Object.assign({}, PUB, { chain: { exists: true, shared: true } }) });
    await monter(<InvitationDuo token="T0" />);
    expect(par('wf-etape-3')).not.toBeNull();
    expect(par('invitation-form')).not.toBeNull();
    expect(axios.post).not.toHaveBeenCalled();
  });

  // V556 : sans la clé de CET appareil (autre téléphone), message clair, aucune
  // erreur technique, aucun bouton de partage ni formulaire qui échouerait (403).
  test('chain.exists sans clé locale : message « autre appareil », ni champs ni partage', async () => {
    axios.post.mockResolvedValue({ status: 200, data: { child: CHILD(3), shared: false, preview: PREVIEW_OK } });
    axios.get.mockResolvedValue({ data: Object.assign({}, PUB, { chain: { exists: true, shared: false } }) });
    await monter(<InvitationDuo token="T0" />);
    await allerALaCarte();
    expect(par('wf-autre-appareil')).not.toBeNull();
    expect(conteneur.textContent).toContain("Pour protéger ton invitation, termine l'inscription sur l'appareil avec lequel tu as partagé ton invitation.");
    expect(par('wf-whatsapp')).toBeNull();
    expect(par('wf-nom')).toBeNull();
    expect(par('wf-copier-page')).not.toBeNull();
  });

  test('déjà partagée depuis un autre appareil : étape 3 SANS formulaire, message clair', async () => {
    axios.get.mockResolvedValue({ data: Object.assign({}, PUB, { chain: { exists: true, shared: true } }) });
    await monter(<InvitationDuo token="T0" />);
    expect(par('wf-etape-3')).not.toBeNull();
    expect(par('invitation-form')).toBeNull();
    expect(par('wf-autre-appareil')).not.toBeNull();
    expect(par('wf-partager-encore')).toBeNull();
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('409 invitation_requise au join → retour à l\'étape 2 avec le message', async () => {
    window.localStorage.setItem(cleChaine('T0'), 'K1'); // même appareil que le partage
    routerPost({ join: () => Promise.reject({ response: { status: 409, headers: { 'x-refus-raison': 'invitation_requise' }, data: {} } }) });
    axios.get.mockResolvedValue({ data: Object.assign({}, PUB, { chain: { exists: true, shared: true } }) });
    await monter(<InvitationDuo token="T0" />);
    const remplir = (id, v) => {
      const el = par(id);
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true }));
    };
    await act(async () => {
      remplir('invitation-prenom', 'Aminata'); remplir('invitation-email', 'a@b.ch'); remplir('invitation-whatsapp', '+41790000000');
    });
    await cliquer('invitation-consent');
    await act(async () => { par('invitation-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });
    await vider();
    expect(par('wf-etape-partage')).not.toBeNull();
    expect(par('wf-avis').textContent).toBe(messageRefus('invitation_requise'));
    expect(axios.post.mock.calls.some((c) => String(c[0]).endsWith('/chain'))).toBe(true);
  });

  test('succès du join en mode chaîne : l\'invitation reste active', async () => {
    window.localStorage.setItem(cleChaine('T0'), 'K1'); // même appareil que le partage
    routerPost();
    axios.get.mockResolvedValue({ data: Object.assign({}, PUB, { chain: { exists: true, shared: true } }) });
    await monter(<InvitationDuo token="T0" />);
    const remplir = (id, v) => {
      const el = par(id);
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true }));
    };
    await act(async () => {
      remplir('invitation-prenom', 'Aminata'); remplir('invitation-email', 'a@b.ch'); remplir('invitation-whatsapp', '+41790000000');
    });
    await cliquer('invitation-consent');
    await act(async () => { par('invitation-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });
    await vider();
    expect(par('invitation-chaine-active').textContent).toContain('Ton invitation reste active');
  });

  test('« Partager avec la carte » seulement si canShare({files}) ; share résolu → POST share_image', async () => {
    routerPost();
    const blob = new Blob(['x'], { type: 'image/jpeg' });
    global.fetch = jest.fn((url) => (String(url).includes('carte.jpg')
      ? Promise.resolve({ ok: true, headers: { get: () => 'image/jpeg' }, blob: () => Promise.resolve(blob) })
      : Promise.resolve({ ok: true, headers: { get: () => 'text/html' },
        text: () => Promise.resolve('<html><head><meta property="og:title" content="t"><meta property="og:description" content="d"><meta property="og:image" content="https://afroboost.com/i.jpg"></head></html>') })));
    navigator.share = jest.fn(() => Promise.resolve());
    navigator.canShare = jest.fn(() => true);
    axios.get.mockResolvedValue({ data: PUB });
    await monter(<InvitationDuo token="T0" />);
    await allerAuPartage();
    expect(par('wf-apercu-simplifie')).toBeNull();
    await cliquer('wf-partager'); // V560 : « Partager » joint la carte quand le téléphone le permet
    const arg = navigator.share.mock.calls[0][0];
    expect(arg.files[0].name).toBe('invitation-afroboost.jpg');
    expect(arg.text).toContain('/duo/T1?v=3');
    expect(axios.post.mock.calls.find((c) => String(c[0]).endsWith('/chain/share'))[1]).toEqual({ channel: 'share_image' });
    expect(par('wf-etape-3')).not.toBeNull();
  });

  test('partage annulé (AbortError) → rien enregistré, on reste à l\'étape 2', async () => {
    routerPost();
    navigator.share = jest.fn(() => Promise.reject(Object.assign(new Error('x'), { name: 'AbortError' })));
    axios.get.mockResolvedValue({ data: PUB });
    await monter(<InvitationDuo token="T0" />);
    await allerAuPartage();
    expect(par('wf-partager-carte')).toBeNull(); // pas de fichier : pas de partage avec carte
    await cliquer('wf-partager');
    expect(axios.post.mock.calls.some((c) => String(c[0]).endsWith('/chain/share'))).toBe(false);
    expect(par('wf-etape-partage')).not.toBeNull();
  });

  test('409 chaine_en_attente à la création → message FR + Réessayer', async () => {
    axios.post.mockRejectedValue({ response: { status: 409, headers: { 'x-refus-raison': 'chaine_en_attente' }, data: {} } });
    axios.get.mockResolvedValue({ data: PUB });
    await monter(<InvitationDuo token="T0" />);
    await allerALaCarte();
    expect(par('wf-erreur-creation').textContent).toContain(messageRefus('chaine_en_attente'));
    expect(par('wf-reessayer-creation')).not.toBeNull();
  });

  test('verifierApercuNavigateur ne rejette jamais (fetch absent → ok:false)', async () => {
    const v = await verifierApercuNavigateur({ cardUrl: 'https://x/c.jpg', shareUrl: 'https://x/s' });
    expect(v.ok).toBe(false);
    expect(v.file).toBeNull();
  });

  test('aucun hex en dur hors valeur de secours dans les nouveaux fichiers', () => {
    ['../WizardFilleul.js', '../wizardFilleul.css'].forEach((f) => {
      const src = fs.readFileSync(path.join(__dirname, f), 'utf8');
      const hexes = src.match(/#[0-9a-fA-F]{3,8}\b/g) || [];
      hexes.forEach((h) => {
        const idx = src.indexOf(h);
        expect(src.slice(Math.max(0, idx - 40), idx)).toMatch(/var\(--[a-z-]+,\s*$/);
      });
    });
  });
});

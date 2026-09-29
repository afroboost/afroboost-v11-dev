/**
 * V559 — Programme Créateur (écran). axios mocké : aucun réseau.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import fs from 'fs';
import path from 'path';
import EspaceCreateur from '../EspaceCreateur';
import CarteCreateur from '../CarteCreateur';
import AdminCreateurs from '../AdminCreateurs';
import {
  attributionActuelle, attributionEnregistrer, createurActuel, CLE_CREATEUR,
} from '../../../utils/attribution';

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), patch: jest.fn(), delete: jest.fn() },
}));
jest.mock('qrcode.react', () => ({
  QRCodeSVG: (p) => <svg data-testid="qr-svg" data-value={p.value} />,
}));

let conteneur, racine;
beforeEach(() => {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  axios.get.mockReset(); axios.post.mockReset(); axios.put.mockReset();
  window.localStorage.clear();
  global.fetch = undefined;
  window.open = jest.fn(() => null);
});
afterEach(() => {
  if (racine) act(() => racine.unmount());
  racine = null;
  conteneur.remove();
});

const par = (id) => document.querySelector(`[data-testid="${id}"]`);
const vider = () => act(async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); });
async function monter(el) {
  await act(async () => { racine = createRoot(conteneur); racine.render(el); });
  await vider();
}
const cliquer = async (id) => { await act(async () => { par(id).click(); }); await vider(); };
const saisir = async (id, v) => {
  const el = par(id);
  const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  await act(async () => {
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
};

const DASH = {
  kpis: { gains_totaux: 19, en_attente: 4, solde: 15, achats: 3, filleuls: 2 },
  lien: 'https://afroboost.com/?createur=jetonLea12345', lien_partage: 'https://afroboost.com/api/createur/partage/jetonLea12345',
  carte_url: 'https://afroboost.com/api/createur/partage/jetonLea12345/carte.jpg',
  commissions: ['Pulse X10 : 15.00 CHF', 'Soirée Afro : 10 %'], retrait_min: 10, retrait_possible: true,
  retrait_en_cours: false, methode: 'twint', methode_detail: '•••• 3040', retraits: [],
  filleuls: [{ prenom: 'Sophie', date: '2026-09-29T10:00:00Z', origine: 'Lien créateur', statut: 'Achat confirmé' }],
  conversions: [{ id: 'c1', date: '2026-09-29T10:00:00Z', offre: 'Pulse X10', montant: 150, commission: 15, statut: 'confirmed', statut_libelle: 'Confirmée' }],
};
const ME = (statut, extra) => Object.assign({ statut, role: 'subscriber', programme_ouvert: true,
  commissions: DASH.commissions, delai_confirmation_jours: 14, retrait_min: 10 }, extra || {});

describe('V559 — lien créateur (attribution)', () => {
  test('?createur= mémorisé 30 jours, voyage dans attributionActuelle() même sans UTM ; jeton invalide ignoré', () => {
    attributionEnregistrer('?createur=abc', '', '/');
    expect(createurActuel()).toBe('');
    expect(attributionActuelle()).toBeNull();
    attributionEnregistrer('?createur=jetonLea12345', '', '/');
    expect(attributionActuelle()).toEqual({ first: null, last: null, createur: 'jetonLea12345' });
    attributionEnregistrer('?utm_source=instagram', '', '/');
    expect(attributionActuelle().first.source).toBe('instagram');
    expect(attributionActuelle().createur).toBe('jetonLea12345');
    window.localStorage.setItem(CLE_CREATEUR, JSON.stringify({ t: 'jetonLea12345', at: Date.now() - 31 * 86400000 }));
    expect(createurActuel()).toBe('');
  });
});

describe('V559 — Devenir créateur', () => {
  test('statut none → principe + barème + formulaire ; règlement obligatoire ; l’e-mail ne part jamais du navigateur', async () => {
    axios.get.mockResolvedValue({ data: ME('none') });
    axios.post.mockResolvedValue({ data: ME('pending') });
    const entetes = () => ({ 'x-espace-token': 'tok' });
    await monter(<EspaceCreateur entetes={entetes} />);
    expect(axios.get.mock.calls[0][1].headers).toEqual({ 'x-espace-token': 'tok' });
    expect(par('devenir-createur').textContent).toContain('Recommande Afroboost à ton réseau et gagne une commission');
    expect(par('cr-bareme').textContent).toContain('Pulse X10 : 15.00 CHF');
    await saisir('cr-prenom', 'Léa'); await saisir('cr-nom', 'Parrain');
    await saisir('cr-telephone', '079 200 30 40'); await saisir('cr-motivation', 'Coach de danse');
    await act(async () => { par('cr-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });
    await vider();
    expect(axios.post).not.toHaveBeenCalled();
    expect(par('cr-form-erreur').textContent).toContain('règlement');
    await cliquer('cr-reglement');
    await act(async () => { par('cr-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });
    await vider();
    const [url, corps] = axios.post.mock.calls[0];
    expect(url).toMatch(/\/api\/createur\/demande$/);
    expect(corps).toEqual(expect.objectContaining({ prenom: 'Léa', nom: 'Parrain', telephone: '079 200 30 40',
      payout_method: 'twint', reglement_accepte: true }));
    expect(corps).not.toHaveProperty('email');
    expect(par('cr-en-attente').textContent).toContain('en cours d’examen');
  });

  test('statut approved → Dashboard Créateur : 4 KPI, lien + Copier + QR, partages, barème, filleuls, conversions', async () => {
    axios.get.mockResolvedValue({ data: ME('approved', { dashboard: DASH }) });
    Object.assign(navigator, { clipboard: { writeText: jest.fn().mockResolvedValue() } });
    await monter(<EspaceCreateur entetes={() => ({})} />);
    expect(par('creator-dashboard').textContent).toContain('Suis tes revenus et tes filleuls en temps réel');
    expect(par('cr-kpi-gains').textContent).toContain('19.00 CHF');
    expect(par('cr-kpi-attente').textContent).toContain('4.00 CHF');
    expect(par('cr-kpi-filleuls').textContent).toContain('2');
    expect(par('cr-kpi-achats').textContent).toContain('3');
    expect(par('cr-lien-texte').textContent).toBe('afroboost.com/?createur=jetonLea12345');
    await cliquer('cr-qr');
    expect(par('qr-svg').getAttribute('data-value')).toBe(DASH.lien);
    await cliquer('cr-whatsapp');
    expect(decodeURIComponent(String(window.open.mock.calls[0][0]))).toContain(DASH.lien_partage);
    expect(par('cr-commission').textContent).toContain('Soirée Afro : 10 %');
    expect(par('cr-filleuls').textContent).toContain('Sophie');
    expect(par('cr-filleuls').textContent).toContain('Achat confirmé');
    expect(par('cr-conversions').textContent).toContain('Pulse X10');
    expect(par('cr-conversions').textContent).toContain('15.00 CHF');
    expect(par('cr-conversions').textContent).toContain('Confirmée');
  });

  test('« Demander un retrait » → POST /retrait, puis l’état renvoyé ; désactivé sous le minimum', async () => {
    axios.get.mockResolvedValue({ data: ME('approved', { dashboard: DASH }) });
    axios.post.mockResolvedValue({ data: ME('approved', { dashboard: Object.assign({}, DASH, {
      retrait_possible: false, retrait_en_cours: true, kpis: Object.assign({}, DASH.kpis, { solde: 0 }) }) }) });
    await monter(<EspaceCreateur />);
    expect(par('cr-retrait').disabled).toBe(false);
    await cliquer('cr-retrait');
    expect(axios.post.mock.calls[0][0]).toMatch(/\/api\/createur\/retrait$/);
    expect(par('cr-retrait-en-cours')).not.toBeNull();
    expect(par('cr-retrait').disabled).toBe(true);
  });
});

describe('V559 — accès espace abonné et console', () => {
  test('carte : « Devenir créateur Afroboost » puis « Dashboard Créateur » selon le statut serveur', async () => {
    axios.get.mockResolvedValue({ data: ME('none') });
    await monter(<CarteCreateur entetes={() => ({})} />);
    expect(par('carte-createur-ouvrir').textContent).toContain('Devenir créateur Afroboost');
    act(() => racine.unmount()); racine = null;
    axios.get.mockResolvedValue({ data: ME('approved', { dashboard: DASH }) });
    await monter(<CarteCreateur entetes={() => ({})} />);
    expect(par('carte-createur-ouvrir').textContent).toContain('Dashboard Créateur');
  });

  test('console : une demande en attente → Approuver envoie la décision puis relit', async () => {
    axios.get.mockResolvedValue({ data: { createurs: [{ id: 'cr1', prenom: 'Léa', nom: 'P', email: 'l@x.ch', telephone: '+41790000000',
      statut: 'pending', role_origine: 'subscriber', methode: 'twint', methode_detail: '•••• 0000', cree_le: '2026-09-29T10:00:00Z' }] } });
    axios.post.mockResolvedValue({ data: {} });
    await monter(<AdminCreateurs />);
    expect(axios.get.mock.calls[0][1].params).toEqual({ statut: 'pending' });
    await cliquer('admin-approuver');
    expect(axios.post.mock.calls[0][0]).toMatch(/\/admin\/createurs\/cr1\/decision$/);
    expect(axios.post.mock.calls[0][1]).toEqual({ decision: 'approve' });
    expect(axios.get.mock.calls.length).toBe(2);
  });

  test('aucun hex en dur hors valeur de secours dans les fichiers du programme', () => {
    ['../CreatorDashboard.js', '../EspaceCreateur.js', '../CarteCreateur.js', '../AdminCreateurs.js', '../createur.css'].forEach((f) => {
      const src = fs.readFileSync(path.join(__dirname, f), 'utf8');
      (src.match(/#[0-9a-fA-F]{3,8}\b/g) || []).forEach((h) => {
        const idx = src.indexOf(h);
        expect(src.slice(Math.max(0, idx - 40), idx)).toMatch(/var\(--[a-z-]+,\s*$/);
      });
    });
  });
});

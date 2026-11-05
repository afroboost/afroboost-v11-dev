/**
 * V648 — interface du rappel de paiement : aperçu obligatoire, confirmation explicite,
 * aucune action sur les lignes exclues, réglage MANUEL par défaut, aucune boucle d'appels.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import EcheancesPaiement from '../EcheancesPaiement';

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn() }));

const $ = (id) => document.querySelector(`[data-testid="${id}"]`);
const pause = (ms = 0) => act(async () => { await new Promise((r) => setTimeout(r, ms)); });
async function attendre(id) {
  for (let i = 0; i < 40; i += 1) {
    if ($(id)) return $(id);
    await pause(5);       // eslint-disable-line no-await-in-loop
  }
  throw new Error(`élément absent : ${id}`);
}
const clic = (el) => act(async () => { el.click(); });

const ligne = (k = {}) => ({
  subscription_id: 's1', code: 'CODE-1', nom: 'Marie', reste_a_payer: 200, devise: 'CHF', prochaine_echeance: '2026-11-05',
  en_retard: false, paiement_suivant: '2/2', rappel_envoi: { possible: true, motif: null, message: '', dernier: null }, ...k,
});
const APERCU = {
  possible: true, envoi_reel: false, empreinte: 'emp1', destinataire: 'marie@example.test', reste: 200, devise: 'CHF',
  echeance: '2026-11-05', avertissement: '', sujet: 'Rappel : ton deuxième paiement Afroboost',
  texte: "Bonjour Marie,\n\nCoach Bassi, d'Afroboost", code: 'CODE-1', historique: [],
};

function brancher({ rappels = [ligne()], apercu = APERCU, reglages } = {}) {
  axios.get.mockImplementation((url) => {
    if (url.endsWith('/discount-codes/echeances')) return Promise.resolve({ data: { rappels } });
    if (url.endsWith('/apercu')) return Promise.resolve({ data: apercu });
    if (url.endsWith('/reglages')) return Promise.resolve({ data: reglages || { mode: 'MANUEL', delais: ['J-3', 'J0', 'J+3'], automatisation_disponible: false, envoi_reel: false } });
    if (url.endsWith('/simulation')) {
      return Promise.resolve({ data: { simulation: true, aucun_envoi: true, lignes: [
        { code: 'CODE-1', nom: 'Marie', enverrait: true, jalons: [{ palier: 'J0', date: '2026-11-05', etat: 'a_venir' }] },
        { code: 'CODE-S', nom: 'Sam', enverrait: false, message_exclusion: 'Abonnement prélevé par Stripe : aucun rappel à envoyer.', jalons: [] },
      ] } });
    }
    return Promise.reject(new Error(`url inattendue ${url}`));
  });
}

let racine;
let hote;
async function monter() {
  hote = document.createElement('div');
  document.body.appendChild(hote);
  racine = createRoot(hote);
  await act(async () => { racine.render(<EcheancesPaiement />); });
}

beforeEach(() => { jest.resetAllMocks(); });
afterEach(async () => {
  await act(async () => { racine.unmount(); });
  hote.remove();
});

test("une ligne éligible propose le bouton ; rien n'est envoyé à l'ouverture", async () => {
  brancher();
  await monter();
  await clic(await attendre('v648-rappel-CODE-1'));
  expect((await attendre('v648-texte')).textContent).toContain("Coach Bassi, d'Afroboost");
  expect($('v648-destinataire').textContent).toBe('marie@example.test');
  expect($('v648-montant').textContent).toBe('200.00 CHF');
  expect(axios.post).not.toHaveBeenCalled();
});

test('sans la case cochée, le bouton est inerte', async () => {
  brancher();
  await monter();
  await clic(await attendre('v648-rappel-CODE-1'));
  const bouton = await attendre('v648-envoyer');
  expect(bouton.disabled).toBe(true);
  await clic(bouton);
  expect(axios.post).not.toHaveBeenCalled();
});

test("confirmé : le navigateur n'envoie que l'empreinte et la confirmation", async () => {
  brancher();
  axios.post.mockResolvedValue({ data: { issue: 'simulation', envoye: false, message: "Simulation : aucun e-mail n'a été envoyé." } });
  await monter();
  await clic(await attendre('v648-rappel-CODE-1'));
  await clic(await attendre('v648-confirmation'));
  await clic($('v648-envoyer'));
  expect(axios.post).toHaveBeenCalledTimes(1);
  const [url, corps] = axios.post.mock.calls[0];
  expect(url).toContain('/rappels-paiement/s1/envoyer');
  expect(corps).toEqual({ empreinte: 'emp1', confirmation: true, reprise_incertain: false });
  expect((await attendre('v648-resultat')).textContent).toContain('Simulation');
});

test('envoi réel coupé : le coach le lit avant de confirmer', async () => {
  brancher();
  await monter();
  await clic(await attendre('v648-rappel-CODE-1'));
  expect((await attendre('v648-envoi-coupe')).textContent).toContain('aucun e-mail ne partira');
});

test('ligne exclue (saison_2x) : motif affiché, aucun bouton', async () => {
  brancher({ rappels: [ligne({ code: 'CODE-S', rappel_envoi: { possible: false, motif: 'stripe_recurrent', message: 'Abonnement prélevé par Stripe : aucun rappel à envoyer.', dernier: null } })] });
  await monter();
  expect((await attendre('v648-bloque-CODE-S')).textContent).toContain('Stripe');
  expect($('v648-rappel-CODE-S')).toBeNull();
});

test('rappel déjà envoyé pour cette échéance : plus de bouton', async () => {
  brancher({ rappels: [ligne({ rappel_envoi: { possible: true, dernier: { statut: 'envoye', echeance: '2026-11-05', envoye_le: '2026-11-05T08:00:00+00:00' } } })] });
  await monter();
  expect((await attendre('v648-envoye-CODE-1')).textContent).toContain('05.11.2026');
  expect($('v648-rappel-CODE-1')).toBeNull();
});

test("un rappel d'une ANCIENNE échéance ne bloque pas la nouvelle", async () => {
  brancher({ rappels: [ligne({ rappel_envoi: { possible: true, dernier: { statut: 'envoye', echeance: '2026-10-01', envoye_le: '2026-10-01T08:00:00+00:00' } } })] });
  await monter();
  expect(await attendre('v648-rappel-CODE-1')).toBeTruthy();
});

test('envoi incertain : le texte le dit, et la reprise le demande explicitement', async () => {
  brancher({
    rappels: [ligne({ rappel_envoi: { possible: true, dernier: { statut: 'incertain', echeance: '2026-11-05' } } })],
    apercu: { ...APERCU, historique: [{ palier: 'manuel', echeance: '2026-11-05', statut: 'incertain', montant: 200, devise: 'CHF' }] },
  });
  axios.post.mockResolvedValue({ data: { envoye: true, message: 'Rappel envoyé.' } });
  await monter();
  expect((await attendre('v648-statut-CODE-1')).textContent).toContain('peut-être parti');
  await clic($('v648-rappel-CODE-1'));
  expect(await attendre('v648-incertain')).toBeTruthy();
  await clic($('v648-confirmation'));
  await clic($('v648-envoyer'));
  expect(axios.post.mock.calls[0][1].reprise_incertain).toBe(true);
});

test("refus du serveur : le message s'affiche et la confirmation est à refaire", async () => {
  brancher();
  axios.post.mockRejectedValue({ response: { status: 409, data: { detail: { type: 'solde_nul', message: 'Il ne reste rien à payer.' } } } });
  await monter();
  await clic(await attendre('v648-rappel-CODE-1'));
  await clic(await attendre('v648-confirmation'));
  await clic($('v648-envoyer'));
  expect((await attendre('v648-erreur')).textContent).toContain('Il ne reste rien à payer');
  expect($('v648-confirmation').checked).toBe(false);
});

test('aucune boucle : un seul appel à la liste, même dialogue ouvert', async () => {
  brancher();
  await monter();
  await clic(await attendre('v648-rappel-CODE-1'));
  await attendre('v648-texte');
  await pause(50);
  expect(axios.get.mock.calls.filter(([u]) => u.endsWith('/echeances'))).toHaveLength(1);
  expect(axios.get.mock.calls.filter(([u]) => u.endsWith('/apercu'))).toHaveLength(1);
});

test("liste vide : l'encadré disparaît, le réglage reste accessible", async () => {
  brancher({ rappels: [] });
  await monter();
  expect(await attendre('v648-reglages-seuls')).toBeTruthy();
  expect($('v617-echeances')).toBeNull();
});

test("réglage : MANUEL par défaut, les délais n'apparaissent qu'en Automatique", async () => {
  brancher();
  axios.put.mockResolvedValue({ data: {} });
  await monter();
  await clic(await attendre('v648-ouvrir-reglages'));
  expect((await attendre('v648-mode-MANUEL')).checked).toBe(true);
  expect($('v648-delai-J0')).toBeNull();
  await clic($('v648-mode-AUTOMATIQUE'));
  expect((await attendre('v648-auto-coupe')).textContent).toContain('Aucun rappel ne part tout seul');
  expect(axios.put).toHaveBeenCalledWith(expect.stringContaining('/reglages'), { mode: 'AUTOMATIQUE', delais: ['J-3', 'J0', 'J+3'] });
  expect(axios.post).not.toHaveBeenCalled();
});

test('simulation : montre les dates et les exclusions, sans aucun envoi', async () => {
  brancher({ reglages: { mode: 'AUTOMATIQUE', delais: ['J-3', 'J0', 'J+3'], automatisation_disponible: false, envoi_reel: false } });
  await monter();
  await clic(await attendre('v648-ouvrir-reglages'));
  await clic(await attendre('v648-voir-simulation'));
  expect((await attendre('v648-simulation')).textContent).toContain("aucun e-mail n'est envoyé");
  expect($('v648-sim-CODE-1').textContent).toContain('J0 : 05.11.2026');
  expect($('v648-sim-CODE-S').textContent).toContain('Exclu');
  expect(axios.post).not.toHaveBeenCalled();
});

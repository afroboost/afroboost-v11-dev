/**
 * V648 — section « Rappels de paiement » de la page Paiements : aperçu obligatoire, confirmation
 * explicite, montant à vérifier, relances, réglages, aucune boucle d'appels.
 * L'accordéon garde ses 5 sections d'origine et ouvre toujours « Configuration des Paiements ».
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import RappelsPaiementSection from '../RappelPaiement';
import V199BoutiqueAccordion from '../V199BoutiqueAccordion';

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn() }));
jest.mock('../ConceptEditor', () => ({ section }) => <div data-testid={`concept-${section}`} />);
jest.mock('../PaymentConfigTab', () => () => <div data-testid="config-paiements" />);
jest.mock('../InvoiceGenerator', () => () => <div data-testid="factures" />);
jest.mock('../../SvgIcon', () => ({ name }) => <i data-icon={name} />);

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
const saisir = (el, v) => act(async () => {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, v);
  el.dispatchEvent(new Event('input', { bubbles: true }));
});

const ENVOI = { peut_envoyer: true, action: 'nouveau', etape: 'Rappel', delai_jours: 7 };
const ligne = (k = {}) => ({
  subscription_id: 's1', code: 'CODE-1', nom: 'Marie', reste_a_payer: 200, devise: 'CHF', prochaine_echeance: '2026-11-05',
  en_retard: false, paiement_suivant: '2/2', possible: true, motif: null, message: '', verification_requise: false, envoi: ENVOI, ...k,
});
const APERCU = {
  possible: true, envoi_reel: false, empreinte: 'emp1', destinataire: 'marie@example.test', reste: 200, devise: 'CHF',
  echeance: '2026-11-05', avertissement: '', verification_requise: false, envoi: ENVOI,
  sujet: 'Rappel : ton deuxième paiement Afroboost', texte: "Bonjour Marie,\n\nCoach Bassi, d'Afroboost", code: 'CODE-1', historique: [],
};
const REGLAGES = { mode: 'MANUEL', delais: ['J-3', 'J0', 'J+3'], delai_relance_jours: 7, automatisation_disponible: false, envoi_reel: false };

function brancher({ lignes = [ligne()], apercu = APERCU, reglages = REGLAGES, historique = [] } = {}) {
  axios.get.mockImplementation((url) => {
    if (url.endsWith('/liste')) return Promise.resolve({ data: { lignes, envoi_reel: false } });
    if (url.endsWith('/historique')) return Promise.resolve({ data: { historique } });
    if (url.endsWith('/apercu')) return Promise.resolve({ data: apercu });
    if (url.endsWith('/reglages')) return Promise.resolve({ data: reglages });
    if (url.endsWith('/simulation')) {
      return Promise.resolve({ data: { simulation: true, aucun_envoi: true, lignes: [
        { code: 'CODE-1', nom: 'Marie', enverrait: true, jalons: [{ palier: 'J0', date: '2026-11-05', etat: 'a_venir' }] },
        { code: 'CODE-S', nom: 'Sam', enverrait: false, message_exclusion: 'Prélevé automatiquement par Stripe : pas de rappel manuel pour cette échéance.', jalons: [] },
      ] } });
    }
    return Promise.reject(new Error(`url inattendue ${url}`));
  });
}

let racine;
let hote;
async function monter(element = <RappelsPaiementSection />) {
  hote = document.createElement('div');
  document.body.appendChild(hote);
  racine = createRoot(hote);
  await act(async () => { racine.render(element); });
}

beforeEach(() => { jest.resetAllMocks(); });
afterEach(async () => {
  await act(async () => { racine.unmount(); });
  hote.remove();
});

describe('page Paiements', () => {
  const ouvrir = (id) => clic($(`v199-accordion-${id}`).querySelector('[role="button"]'));

  test("les 5 sections d'origine sont là, Configuration ouverte, Rappels fermée et sans appel réseau", async () => {
    brancher();
    await monter(<V199BoutiqueAccordion coachUser={{ email: 'c@example.test' }} />);
    ['payments', 'conditions', 'logos', 'invoices', 'landing', 'rappels'].forEach((id) => expect($(`v199-accordion-${id}`)).toBeTruthy());
    expect($('config-paiements')).toBeTruthy();
    expect($('v648-section')).toBeNull();
    expect(axios.get).not.toHaveBeenCalled();
    expect($('v199-accordion-rappels').textContent).toContain('Rappels de paiement');
  });

  test("ouvrir « Rappels de paiement » ne ferme pas la configuration", async () => {
    brancher();
    await monter(<V199BoutiqueAccordion coachUser={{ email: 'c@example.test' }} />);
    await ouvrir('rappels');
    expect(await attendre('v648-section')).toBeTruthy();
    expect($('config-paiements')).toBeTruthy();
  });
});

test('la section contient le choix, la liste, les montants, les dates et les deux boutons', async () => {
  brancher();
  await monter();
  expect((await attendre('v648-mode-MANUEL')).checked).toBe(true);
  const l = await attendre('v648-ligne-CODE-1');
  expect(l.textContent).toContain('200.00 CHF');
  expect(l.textContent).toContain('05.11.2026');
  expect($('v648-voir-CODE-1').textContent).toBe('Prévisualiser');
  expect($('v648-rappel-CODE-1').textContent).toBe('Envoyer le rappel');
  expect($('v648-historique-general')).toBeTruthy();
  expect($('v648-section-coupe').textContent).toContain('aucun e-mail ne partira');
});

test("Prévisualiser n'offre aucun envoi tant qu'on ne continue pas", async () => {
  brancher();
  await monter();
  await clic(await attendre('v648-voir-CODE-1'));
  expect((await attendre('v648-texte')).textContent).toContain("Coach Bassi, d'Afroboost");
  expect($('v648-confirmation')).toBeNull();
  expect($('v648-envoyer')).toBeNull();
  await clic($('v648-continuer'));
  expect($('v648-confirmation')).toBeTruthy();
  expect(axios.post).not.toHaveBeenCalled();
});

test("Envoyer montre aussi l'aperçu, et le bouton reste inerte sans la case", async () => {
  brancher();
  await monter();
  await clic(await attendre('v648-rappel-CODE-1'));
  expect((await attendre('v648-texte')).textContent).toContain('Bonjour Marie');
  expect($('v648-destinataire').textContent).toBe('marie@example.test');
  const bouton = $('v648-envoyer');
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
  expect(corps).toEqual({ empreinte: 'emp1', confirmation: true });
  expect((await attendre('v648-resultat')).textContent).toContain('Simulation');
});

describe('suivi incomplet (case « en plusieurs fois » non cochée)', () => {
  const INCOMPLET = { ...APERCU, verification_requise: true, avertissement: "Ce solde est un calcul, pas une preuve de non-paiement : vérifie ce qui est réellement dû." };
  const brancherIncomplet = () => brancher({ lignes: [ligne({ verification_requise: true })], apercu: INCOMPLET });

  test("l'envoi reste bloqué tant que le montant n'est pas saisi, même case cochée", async () => {
    brancherIncomplet();
    await monter();
    expect((await attendre('v648-a-verifier-CODE-1')).textContent).toContain('Montant à vérifier');
    await clic($('v648-rappel-CODE-1'));
    expect((await attendre('v648-avertissement')).textContent).toContain('pas une preuve');
    await clic($('v648-confirmation'));
    expect($('v648-envoyer').disabled).toBe(true);
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('le montant saisi part au serveur, qui décide', async () => {
    brancherIncomplet();
    axios.post.mockResolvedValue({ data: { envoye: false, message: 'Simulation' } });
    await monter();
    await clic(await attendre('v648-rappel-CODE-1'));
    await saisir(await attendre('v648-montant-confirme'), '200,00');
    await clic($('v648-confirmation'));
    await clic($('v648-envoyer'));
    expect(axios.post.mock.calls[0][1].montant_confirme).toBe(200);
  });

  test('montant différent : message du serveur, confirmation à refaire, rien de modifié', async () => {
    brancherIncomplet();
    axios.post.mockRejectedValue({ response: { status: 409, data: { detail: { type: 'montant_different', message: 'Ce montant ne correspond pas au solde calculé.' } } } });
    await monter();
    await clic(await attendre('v648-rappel-CODE-1'));
    await saisir(await attendre('v648-montant-confirme'), '150');
    await clic($('v648-confirmation'));
    await clic($('v648-envoyer'));
    expect((await attendre('v648-erreur')).textContent).toContain('ne correspond pas');
    expect($('v648-confirmation').checked).toBe(false);
    expect(axios.put).not.toHaveBeenCalled();
  });
});

test('le mode réel est affiché, sur la ligne et dans l\'aperçu', async () => {
  brancher({ lignes: [ligne({ mode_paiement: 'TWINT' })], apercu: { ...APERCU, mode_paiement: 'TWINT' } });
  await monter();
  expect((await attendre('v649-mode-CODE-1')).textContent).toBe('TWINT');
  await clic($('v648-voir-CODE-1'));
  expect((await attendre('v649-mode-apercu')).textContent).toBe('TWINT');
});

test('paiement à vérifier : aucun bouton, sans parler de Stripe', async () => {
  brancher({ lignes: [ligne({ mode_paiement: 'Paiement à vérifier', possible: false, motif: 'paiement_a_verifier', message: 'Paiement à vérifier : les informations de paiement sont contradictoires ou incomplètes. Aucun rappel possible.', envoi: null })] });
  await monter();
  const b = await attendre('v648-bloque-CODE-1');
  expect(b.textContent).toContain('Paiement à vérifier');
  expect($('v648-ligne-CODE-1').textContent).not.toContain('Stripe');
  expect($('v648-rappel-CODE-1')).toBeNull();
});

test('ligne exclue (saison_2x) : motif affiché, aucun bouton', async () => {
  brancher({ lignes: [ligne({ code: 'CODE-S', possible: false, motif: 'stripe_recurrent', message: 'Prélevé automatiquement par Stripe : pas de rappel manuel pour cette échéance.', envoi: null })] });
  await monter();
  expect((await attendre('v648-bloque-CODE-S')).textContent).toContain('Stripe');
  expect($('v648-rappel-CODE-S')).toBeNull();
  expect($('v648-voir-CODE-S')).toBeNull();
});

describe('relances', () => {
  const BLOQUE = { peut_envoyer: false, action: 'refus', type: 'deja_envoye', etape: 'Rappel', prochaine_le: '2026-11-12T08:00:00+00:00', message: 'Déjà envoyé pour cette échéance. Relance possible le 12.11.2026.', delai_jours: 7 };

  test('avant le délai : plus de bouton d\'envoi, date affichée, aperçu toujours possible', async () => {
    brancher({ lignes: [ligne({ envoi: BLOQUE })], apercu: { ...APERCU, envoi: BLOQUE } });
    await monter();
    expect((await attendre('v648-attente-CODE-1')).textContent).toContain('12.11.2026');
    expect($('v648-rappel-CODE-1')).toBeNull();
    await clic($('v648-voir-CODE-1'));
    expect((await attendre('v648-envoi-bloque')).textContent).toContain('12.11.2026');
    expect($('v648-envoyer')).toBeNull();
    expect($('v648-continuer')).toBeNull();
  });

  test('maximum atteint ou incertain sans issue : aucun envoi, le motif du serveur est affiché', async () => {
    const M = { peut_envoyer: false, action: 'refus', type: 'maximum_atteint', etape: 'Relance 2', message: 'Maximum de 3 rappels atteint pour cette échéance.', delai_jours: 7 };
    brancher({ lignes: [ligne({ envoi: M })], apercu: { ...APERCU, envoi: M } });
    await monter();
    expect((await attendre('v648-attente-CODE-1')).textContent).toContain('Maximum de 3 rappels');
    expect($('v648-rappel-CODE-1')).toBeNull();
    await clic($('v648-voir-CODE-1'));
    expect((await attendre('v648-envoi-bloque')).textContent).toContain('Maximum de 3 rappels');
    expect($('v648-continuer')).toBeNull();
    expect($('v648-envoyer')).toBeNull();
  });

  test('après le délai : « Envoyer la relance », avec confirmation', async () => {
    const R = { ...ENVOI, etape: 'Relance 1' };
    brancher({ lignes: [ligne({ envoi: R })], apercu: { ...APERCU, envoi: R } });
    await monter();
    const b = await attendre('v648-rappel-CODE-1');
    expect(b.textContent).toBe('Envoyer la relance');
    await clic(b);
    expect((await attendre('v648-envoyer')).disabled).toBe(true);
    expect($('v648-envoyer').textContent).toContain('Relance 1');
  });

  test("l'historique général montre date, destinataire, étape, résultat et coach", async () => {
    brancher({ historique: [{ code: 'CODE-1', palier: 'manuel', rang: 2, etape: 'Relance 1', statut: 'envoye', echeance: '2026-11-05', montant: 200, devise: 'CHF', destinataire: 'marie@example.test', envoye_le: '2026-11-12T08:00:00+00:00', envoye_par: 'coach@example.test' }] });
    await monter();
    const h = await attendre('v648-historique-general');
    await pause(10);
    ['Relance 1', 'Envoyé', '12.11.2026', 'marie@example.test', 'coach@example.test'].forEach((x) => expect(h.textContent).toContain(x));
  });
});

describe('envoi à vérifier', () => {
  const B = { peut_envoyer: false, action: 'refus', type: 'incertain_bloque', etape: 'Rappel', message: 'Envoi à vérifier : contacte la personne directement, hors du système.', a_verifier: true, verification_admin: false, delai_jours: 7 };

  test('statut visible ; un coach ordinaire ne voit aucune action de résolution', async () => {
    brancher({ lignes: [ligne({ envoi: B })], apercu: { ...APERCU, envoi: B } });
    await monter();
    expect((await attendre('v648-a-verifier-envoi-CODE-1')).textContent).toBe('Envoi à vérifier');
    await clic($('v648-voir-CODE-1'));
    expect((await attendre('v648-envoi-bloque')).textContent).toContain('hors du système');
    expect($('v648-verifier')).toBeNull();
    expect($('v648-envoyer')).toBeNull();
  });

  test('super-admin : vérifier la preuve ne passe jamais par la route d\'envoi', async () => {
    const A = { ...B, verification_admin: true };
    brancher({ lignes: [ligne({ envoi: A })], apercu: { ...APERCU, envoi: A } });
    axios.post.mockResolvedValue({ data: { resolu: false, message: 'Aucune trace. Le blocage reste.' } });
    await monter();
    await clic(await attendre('v648-voir-CODE-1'));
    await saisir(await attendre('v648-resend-id'), 'abc-12345');
    await clic($('v648-verifier'));
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.post.mock.calls[0][0]).toContain('/s1/verifier-envoi');
    expect(axios.post.mock.calls[0][1]).toEqual({ resend_id: 'abc-12345' });
    expect((await attendre('v648-preuve')).textContent).toContain('Le blocage reste');
    expect($('v648-envoyer')).toBeNull();
  });

  test('super-admin : la vérification d\'absence ne passe pas non plus par la route d\'envoi', async () => {
    const A = { ...B, verification_admin: true };
    brancher({ lignes: [ligne({ envoi: A })], apercu: { ...APERCU, envoi: A } });
    axios.post.mockResolvedValue({ data: { resolu: false, message: 'Le blocage reste.' } });
    await monter();
    await clic(await attendre('v648-voir-CODE-1'));
    await clic(await attendre('v648-verifier-absence'));
    expect(axios.post.mock.calls[0][0]).toContain('/s1/verifier-envoi');
    expect(axios.post.mock.calls[0][1]).toEqual({ verifier_absence: true });
    expect($('v648-envoyer')).toBeNull();
  });

  test('aucune reprise proposée : la ligne n\'a que « Prévisualiser »', async () => {
    brancher({ lignes: [ligne({ envoi: B })], apercu: { ...APERCU, envoi: B } });
    await monter();
    await attendre('v648-a-verifier-envoi-CODE-1');
    expect($('v648-rappel-CODE-1')).toBeNull();
    expect($('v648-voir-CODE-1')).toBeTruthy();
  });
});

describe('signature du partenaire', () => {
  test('Afroboost : aucun champ, la signature officielle ne se modifie pas', async () => {
    brancher({ reglages: { ...REGLAGES, signature_officielle: true } });
    await monter();
    await attendre('v648-mode-MANUEL');
    expect($('v648-signature')).toBeNull();
  });

  test('partenaire : deux champs, et le refus du serveur est affiché tel quel', async () => {
    brancher({ reglages: { ...REGLAGES, signature_officielle: false, signature: { nom: '', activite: '' } } });
    axios.put.mockRejectedValue({ response: { status: 400, data: { detail: { type: 'nom_refuse', champ: 'nom', message: "Nom : Pas de lien ni d'adresse de site." } } } });
    await monter();
    await saisir(await attendre('v648-signature-nom'), 'evil.com');
    await saisir($('v648-signature-activite'), 'Danse');
    await clic($('v648-signature-enregistrer'));
    expect(axios.put).toHaveBeenCalledWith(expect.stringContaining('/signature'), { nom: 'evil.com', activite: 'Danse' });
    expect((await attendre('v648-signature-refus')).textContent).toContain('Pas de lien');
  });

  test('accepté : la signature telle qu\'elle partira est montrée', async () => {
    brancher({ reglages: { ...REGLAGES, signature_officielle: false, signature: { nom: '', activite: '' } } });
    axios.put.mockResolvedValue({ data: { apercu: "Fit24\nCoach partenaire d'Afroboost" } });
    await monter();
    await saisir(await attendre('v648-signature-nom'), 'Fit24');
    await clic($('v648-signature-enregistrer'));
    expect((await attendre('v648-signature-apercu')).textContent).toContain('Coach partenaire');
  });
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

test('aucune boucle : un seul appel à chaque route, même dialogue ouvert', async () => {
  brancher();
  await monter();
  await clic(await attendre('v648-rappel-CODE-1'));
  await attendre('v648-texte');
  await pause(50);
  ['/liste', '/historique', '/reglages', '/apercu'].forEach((u) => {
    expect(axios.get.mock.calls.filter(([x]) => x.endsWith(u))).toHaveLength(1);
  });
});

test('réglage : MANUEL par défaut, les délais automatiques n\'apparaissent qu\'en Automatique', async () => {
  brancher();
  axios.put.mockResolvedValue({ data: {} });
  await monter();
  expect((await attendre('v648-mode-MANUEL')).checked).toBe(true);
  expect($('v648-delai-J0')).toBeNull();
  await clic($('v648-mode-AUTOMATIQUE'));
  expect((await attendre('v648-auto-coupe')).textContent).toContain('Aucun rappel ne part tout seul');
  expect(axios.put).toHaveBeenCalledWith(expect.stringContaining('/reglages'), { mode: 'AUTOMATIQUE', delais: ['J-3', 'J0', 'J+3'], delai_relance_jours: 7 });
  expect(axios.post).not.toHaveBeenCalled();
});

test('délai de relance : 7 par défaut, réglable, refus du serveur affiché et valeur rétablie', async () => {
  brancher();
  axios.put.mockRejectedValue({ response: { status: 400, data: { detail: 'Délai de relance : entre 1 et 60 jours.' } } });
  await monter();
  const champ = await attendre('v648-delai-relance');
  expect(champ.value).toBe('7');
  await saisir(champ, '99');
  await act(async () => { champ.focus(); champ.blur(); });
  expect((await attendre('v648-reglages-erreur')).textContent).toContain('entre 1 et 60');
  expect(axios.put.mock.calls[0][1].delai_relance_jours).toBe(99);
});

test('simulation : montre les dates et les exclusions, sans aucun envoi', async () => {
  brancher({ reglages: { ...REGLAGES, mode: 'AUTOMATIQUE' } });
  await monter();
  await clic(await attendre('v648-voir-simulation'));
  expect((await attendre('v648-simulation')).textContent).toContain("aucun e-mail n'est envoyé");
  expect($('v648-sim-CODE-1').textContent).toContain('J0 : 05.11.2026');
  expect($('v648-sim-CODE-S').textContent).toContain('Exclu');
  expect(axios.post).not.toHaveBeenCalled();
});

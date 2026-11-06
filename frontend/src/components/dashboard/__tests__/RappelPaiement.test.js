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

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() }));
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
  Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(el, v);
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

describe('menu ⋯ : annuler, exclure, réactiver', () => {
  const ACTIONS = { annuler_un: true, annuler_tous: true, exclure: true, reactiver: false };
  const ouvrir = async (l) => {
    brancher({ lignes: [l] });
    await monter();
    await clic(await attendre('v652-menu-CODE-1'));
    await attendre('v652-menu-contenu-CODE-1');
  };

  test('le menu ne propose que ce que le serveur permet, sans aucun appel', async () => {
    await ouvrir(ligne({ actions: { annuler_un: false, annuler_tous: false, exclure: false, reactiver: true } }));
    expect($('v652-action-reactiver-CODE-1')).not.toBeNull();
    expect($('v652-action-exclure-CODE-1')).toBeNull();
    expect($('v652-action-annuler_un-CODE-1')).toBeNull();
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('sans action permise : pas de menu', async () => {
    brancher({ lignes: [ligne()] });
    await monter();
    await attendre('v648-ligne-CODE-1');
    expect($('v652-menu-CODE-1')).toBeNull();
  });

  test('annuler ce rappel : confirmation, numéro vu, motif, puis relecture', async () => {
    axios.post.mockResolvedValue({ data: { annule: true, message: 'Rappel annulé.' } });
    await ouvrir(ligne({ actions: ACTIONS, envoi: { ...ENVOI, numero: 2 } }));
    await clic($('v652-action-annuler_un-CODE-1'));
    await attendre('v652-confirmer');
    expect(axios.post).not.toHaveBeenCalled();
    await saisir($('v652-motif'), ' Payé en espèces ');
    const avant = axios.get.mock.calls.filter(([u]) => u.endsWith('/liste')).length;
    await clic($('v652-confirmer-action'));
    expect(axios.post.mock.calls[0][0]).toContain('/rappels-paiement/s1/annuler');
    expect(axios.post.mock.calls[0][1]).toEqual({ confirmation: true, portee: 'un', numero: 2, motif: 'Payé en espèces' });
    expect((await attendre('v652-note')).textContent).toBe('Rappel annulé.');
    expect($('v652-confirmer')).toBeNull();
    expect(axios.get.mock.calls.filter(([u]) => u.endsWith('/liste')).length).toBe(avant + 1);
  });

  test('échéance lointaine : le numéro vient de la ligne', async () => {
    axios.post.mockResolvedValue({ data: { message: 'ok' } });
    await ouvrir(ligne({ actions: ACTIONS, envoi: null, possible: false, numero_rappel: 1 }));
    await clic($('v652-action-annuler_un-CODE-1'));
    await clic(await attendre('v652-confirmer-action'));
    expect(axios.post.mock.calls[0][1]).toEqual({ confirmation: true, portee: 'un', numero: 1 });
  });

  test.each([
    ['annuler_tous', '/annuler', { confirmation: true, portee: 'tous' }],
    ['exclure', '/exclure', { confirmation: true }],
  ])('%s : la bonne route', async (nom, route, corps) => {
    axios.post.mockResolvedValue({ data: { message: 'ok' } });
    await ouvrir(ligne({ actions: ACTIONS }));
    await clic($(`v652-action-${nom}-CODE-1`));
    await clic(await attendre('v652-confirmer-action'));
    expect(axios.post.mock.calls[0][0].endsWith(route)).toBe(true);
    expect(axios.post.mock.calls[0][1]).toEqual(corps);
  });

  test('reprendre : proposé seulement si le serveur le permet, avec confirmation', async () => {
    axios.post.mockResolvedValue({ data: { message: 'Rappels repris.' } });
    await ouvrir(ligne({ actions: { reprendre: true, exclure: true } }));
    expect($('v652-action-annuler_tous-CODE-1')).toBeNull();
    await clic($('v652-action-reprendre-CODE-1'));
    await attendre('v652-confirmer');
    expect(axios.post).not.toHaveBeenCalled();
    expect($('v652-confirmer').textContent).toContain('Rien n\'est envoyé');
    await clic($('v652-confirmer-action'));
    expect(axios.post.mock.calls[0][0].endsWith('/reprendre')).toBe(true);
    expect(axios.post.mock.calls[0][1]).toEqual({ confirmation: true });
    expect((await attendre('v652-note')).textContent).toBe('Rappels repris.');
  });

  test('abonnements inactifs : à part, repliés, avec leur solde', async () => {
    brancher({ lignes: [ligne(), ligne({ code: 'CODE-I', subscription_id: 'si', motif: 'abonnement_suspendu', possible: false, statut_rappel: { code: 'suspendu', libelle: 'Suspendu' } })] });
    await monter();
    await attendre('v648-ligne-CODE-1');
    expect($('v648-liste').querySelector('[data-testid="v648-ligne-CODE-I"]')).toBeNull();
    expect($('v652-inactifs').open).toBe(false);
    expect($('v652-inactifs').querySelector('summary').textContent).toBe('Abonnements inactifs (1)');
    expect($('v652-inactifs').textContent).toContain('200.00 CHF');
  });

  test('seulement des abonnements inactifs : pas de liste principale', async () => {
    brancher({ lignes: [ligne({ motif: 'abonnement_suspendu', possible: false })] });
    await monter();
    await attendre('v652-inactifs');
    expect($('v648-liste')).toBeNull();
    expect($('v648-liste-vide')).not.toBeNull();
  });

  test('réactiver : la bonne route, rien d\'autre', async () => {
    axios.post.mockResolvedValue({ data: { message: 'Rappels réactivés.' } });
    await ouvrir(ligne({ actions: { reactiver: true } }));
    await clic($('v652-action-reactiver-CODE-1'));
    await clic(await attendre('v652-confirmer-action'));
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.post.mock.calls[0][0].endsWith('/reactiver')).toBe(true);
  });

  test('refus du serveur : message, fenêtre ouverte, confirmation à refaire', async () => {
    axios.post.mockRejectedValue({ response: { status: 409, data: { detail: { type: 'en_cours', message: 'Un envoi est déjà en cours.' } } } });
    await ouvrir(ligne({ actions: ACTIONS }));
    await clic($('v652-action-annuler_un-CODE-1'));
    await clic(await attendre('v652-confirmer-action'));
    expect((await attendre('v652-erreur')).textContent).toContain('déjà en cours');
    expect($('v652-confirmer-action').disabled).toBe(false);
    expect($('v652-note')).toBeNull();
  });

  test.each([
    ['exclu', 'Exclu'], ['suspendu', 'Suspendu'], ['annule', 'Annulé'], ['envoye', 'Envoyé'],
  ])('statut %s affiché', async (code, libelle) => {
    brancher({ lignes: [ligne({ statut_rappel: { code, libelle } })] });
    await monter();
    expect((await attendre('v652-statut-CODE-1')).textContent).toBe(libelle);
  });

  test('statut Programmé : avec sa date', async () => {
    brancher({ lignes: [ligne({ statut_rappel: { code: 'programme', libelle: 'Programmé', date: '2026-11-09' } })] });
    await monter();
    expect((await attendre('v652-statut-CODE-1')).textContent).toBe('Programmé 09.11.2026');
  });

  test("l'historique montre une annulation et son motif", async () => {
    brancher({ historique: [{ code: 'CODE-1', etape: 'Rappel', statut: 'annule_tous', maj_le: '2026-11-05', echeance: '2026-11-05', palier: 'manuel', rang: 0, destinataire: 'm@example.test', montant: 200, devise: 'CHF', envoye_par: 'coach@example.test', motif_action: 'Arrangement' }] });
    await monter();
    expect((await attendre('v652-histo-motif')).textContent).toContain('Arrangement');
    expect($('v648-historique-general').textContent).toContain('Rappels futurs annulés');
  });
});

test('réglage : MANUEL par défaut, les délais automatiques n\'apparaissent qu\'en Automatique', async () => {
  brancher();
  axios.put.mockResolvedValue({ data: {} });
  await monter();
  expect((await attendre('v648-mode-MANUEL')).checked).toBe(true);
  expect($('v648-delai-J0')).toBeNull();
  await clic($('v648-mode-AUTOMATIQUE'));
  expect((await attendre('v650-auto-demande')).textContent).toContain('De vrais e-mails partiront');
  expect(axios.put).not.toHaveBeenCalled();
  await clic($('v650-auto-annuler'));
  expect($('v650-auto-demande')).toBeNull();
  expect($('v648-mode-MANUEL').checked).toBe(true);
  await clic($('v648-mode-AUTOMATIQUE'));
  await clic(await attendre('v650-auto-confirmer'));
  expect((await attendre('v648-auto-coupe')).textContent).toContain("tant que l'administration");
  expect($('v650-politique').textContent).toContain('tous les 7 jours');
  expect(axios.put).toHaveBeenCalledWith(expect.stringContaining('/reglages'), { mode: 'AUTOMATIQUE', delais: ['J-3', 'J0', 'J+3'], delai_relance_jours: 7, confirmation_auto: true });
  expect(axios.post).not.toHaveBeenCalled();
});

test('automatique ouvert : état annoncé, et retour en manuel sans confirmation', async () => {
  brancher({ reglages: { ...REGLAGES, mode: 'AUTOMATIQUE', automatisation_disponible: true } });
  axios.put.mockResolvedValue({ data: {} });
  await monter();
  expect((await attendre('v650-auto-actif')).textContent).toContain('activé');
  await clic($('v648-mode-MANUEL'));
  expect(axios.put.mock.calls[0][1].mode).toBe('MANUEL');
  expect(axios.put.mock.calls[0][1].confirmation_auto).toBeUndefined();
});

describe('éditeur et aide IA', () => {
  const MODELE = { sujet: 'Rappel : ton deuxième paiement Afroboost', corps: '{bonjour}\n\nReste {montant}, le {echeance}.' };
  const AP = { ...APERCU, modele: MODELE, modele_defaut: MODELE };
  const ouvrir = async () => {
    await monter();
    await clic(await attendre('v648-rappel-CODE-1'));
    return attendre('v650-corps');
  };

  test("un texte modifié bloque l'envoi jusqu'à l'aperçu, puis part avec ce texte", async () => {
    brancher({ apercu: AP });
    const nouveau = { ...AP, empreinte: 'emp2', sujet: 'Rappel : ton deuxième paiement Afroboost', modele: { ...MODELE, corps: '{montant} {echeance} merci' } };
    axios.post.mockImplementation((url) => Promise.resolve({ data: url.endsWith('/apercu') ? nouveau : { issue: 'envoye', envoye: true, message: 'E-mail envoyé.' } }));
    const corps = await ouvrir();
    await clic($('v648-confirmation'));
    await saisir(corps, '{montant} {echeance} merci');
    expect($('v650-a-revoir')).not.toBeNull();
    expect($('v648-envoyer').disabled).toBe(true);
    await clic($('v650-actualiser'));
    await attendre('v648-confirmation');
    expect($('v650-a-revoir')).toBeNull();
    expect($('v648-confirmation').checked).toBe(false);
    await clic($('v648-confirmation'));
    await clic($('v648-envoyer'));
    const envoi = axios.post.mock.calls.find(([u]) => u.endsWith('/envoyer'))[1];
    expect(envoi).toEqual({ empreinte: 'emp2', confirmation: true, sujet: MODELE.sujet, corps: '{montant} {echeance} merci' });
    expect((await attendre('v648-resultat')).textContent).toBe('E-mail envoyé.');
  });

  test("texte refusé par le serveur : le message s'affiche, rien ne part", async () => {
    brancher({ apercu: AP });
    axios.post.mockRejectedValue({ response: { status: 400, data: { detail: { type: 'modele_refuse', message: 'Pas de chiffres dans le texte' } } } });
    const corps = await ouvrir();
    await saisir(corps, 'Payez 500');
    await clic($('v650-actualiser'));
    expect((await attendre('v648-erreur')).textContent).toContain('Pas de chiffres');
    expect(axios.post.mock.calls.some(([u]) => u.endsWith('/envoyer'))).toBe(false);
  });

  test("l'IA propose : le texte ne change qu'après acceptation, et le ton choisi part", async () => {
    brancher({ apercu: AP });
    const prop = { sujet: 'Coucou', corps: '{montant} {echeance} proposition' };
    axios.post.mockResolvedValue({ data: { proposition: prop } });
    const corps = await ouvrir();
    await act(async () => {
      const sel = $('v650-ton');
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(sel, 'direct');
      sel.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await clic($('v650-aide-ia'));
    expect(axios.post.mock.calls[0][1].ton).toBe('direct');
    expect((await attendre('v650-proposition')).textContent).toContain('proposition');
    expect(corps.value).toBe(MODELE.corps);
    await clic($('v650-ignorer'));
    expect($('v650-proposition')).toBeNull();
    expect(corps.value).toBe(MODELE.corps);
    await clic($('v650-aide-ia'));
    await clic(await attendre('v650-accepter'));
    expect(corps.value).toBe(prop.corps);
    expect($('v650-objet').value).toBe('Coucou');
    expect($('v650-a-revoir')).not.toBeNull();
  });

  test('IA en panne : message, texte inchangé', async () => {
    brancher({ apercu: AP });
    axios.post.mockRejectedValue({ response: { status: 502, data: { detail: { type: 'ia_erreur', message: "L'aide IA n'a pas répondu." } } } });
    const corps = await ouvrir();
    await clic($('v650-aide-ia'));
    expect((await attendre('v650-ia-refus')).textContent).toContain("n'a pas répondu");
    expect(corps.value).toBe(MODELE.corps);
  });

  test('garder et réinitialiser le modèle passent par le serveur', async () => {
    brancher({ apercu: AP });
    axios.put.mockResolvedValue({ data: {} });
    axios.delete.mockResolvedValue({ data: {} });
    const corps = await ouvrir();
    await saisir(corps, '{montant} {echeance} a moi');
    await clic($('v650-garder'));
    expect(axios.put).toHaveBeenCalledWith(expect.stringContaining('/modele'), { sujet: MODELE.sujet, corps: '{montant} {echeance} a moi' });
    await clic($('v650-reinitialiser'));
    expect(axios.delete).toHaveBeenCalledWith(expect.stringContaining('/modele'));
    expect((await attendre('v650-corps')).value).toBe(MODELE.corps);
  });

  test("l'historique signale un envoi automatique", async () => {
    brancher({ historique: [{ code: 'CODE-1', etape: 'Rappel', statut: 'envoye', envoye_le: '2026-11-05', echeance: '2026-11-05', palier: 'manuel', rang: 1, destinataire: 'm@example.test', montant: 200, devise: 'CHF', envoye_par: 'automatique', mode_envoi: 'automatique' }] });
    await monter();
    expect((await attendre('v650-histo-auto')).textContent).toContain('Automatique');
  });
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

// V627 — CORBEILLE DES PROSPECTS : bouton, confirmation, motif facultatif, annonce, badge,
// aperçu bloqué, refus de recréation, relances « stoppées ». Prospects FICTIFS.
// Le VRAI ProspectsSection ; `axios` et `useChargement` sont mockés : aucun appel réseau.
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import ProspectsSection, { MOTIFS_CORBEILLE, ModaleCorbeille } from '../ProspectsSection';
import { ligneRelance, lignesRelances, ETATS } from '../../../utils/messagesRelances';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(() => Promise.resolve({ data: {} })), patch: jest.fn(), post: jest.fn(() => Promise.resolve({ data: {} })),
             put: jest.fn(), delete: jest.fn() },
}));

let mockEtatParSection = null;
const mockReessayer = jest.fn();
jest.mock('../../../hooks/useChargement', () => ({
  __esModule: true,
  SECTION: { ATTENTE: 'attente', CHARGEMENT: 'chargement', OK: 'ok', ERREUR: 'erreur', SESSION: 'session' },
  default: (sources) => {
    const sections = {};
    Object.keys(sources).forEach((cle) => {
      const e = (mockEtatParSection && mockEtatParSection[cle]) || { etat: 'ok', donnees: null };
      sections[cle] = { etat: e.etat, donnees: e.donnees, motif: 'serveur' };
    });
    return { sections, reessayer: mockReessayer, global: 'ok', donnees: {}, cles: Object.keys(sources),
             chargement: false, sessionExpiree: false };
  },
}));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;
let conteneur = null;
let racine = null;
async function monter(element) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(element); });
}
afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) document.body.removeChild(conteneur);
  racine = null; conteneur = null; mockEtatParSection = null;
  jest.clearAllMocks();
});
const $ = (t) => document.querySelector(`[data-testid="${t}"]`);
const cliquer = async (el) => { await act(async () => { el.click(); }); };

function conversation(i, sur) {
  const msg = { id: `m-${i}`, action_id: `a-${i}`, recipient_key: `a-${i}`, from_email: `p${i}@exemple.test`,
                subject: 'Re: Proposition', body_text: 'Bonjour', received_at: '2026-10-14T05:25:19+00:00',
                statut: 'rattache', read_at: '2026-10-14T06:00:00+00:00' };
  return Object.assign({ cle: `a-${i}`, action_id: `a-${i}`, organisation: `Studio TEST V627 ${i}`, recipient_key: `a-${i}`,
                         from_email: msg.from_email, nb_messages: 1, message_ids: [msg.id], non_lues: 0,
                         statut_commercial: 'en_attente', dernier_message: msg, dernier_message_at: msg.received_at,
                         messages_recus: [msg], derniere_reponse_afroboost: null, rang: 4,
                         prospect_id: `p-${i}`, categorie: 'association' }, sur || {});
}
function servir(conversations) {
  mockEtatParSection = {
    prospects: { etat: 'ok', donnees: { total: 0, returned: 0, limit: 25, offset: 0, counts: { total: 0, corbeille: 1 }, prospects: [] } },
    campagnes: { etat: 'ok', donnees: { total: 0, campaigns: [] } },
    reponses: { etat: 'ok', donnees: { messages: conversations.map((c) => c.dernier_message), total: conversations.length,
      a_rattacher: 0, conversations, conversations_total: conversations.length,
      conversations_counts: { total: conversations.length, en_attente: conversations.length } } },
  };
}

describe('V627 — la fenêtre de confirmation', () => {
  test('motifs proposés, motif FACULTATIF, avertissement du refus durable, Annuler n’envoie rien', async () => {
    const confirmer = jest.fn();
    const annuler = jest.fn();
    await monter(<ModaleCorbeille cible={{ id: 'p-1', nom: 'Studio TEST' }} onConfirmer={confirmer} onAnnuler={annuler} />);
    expect(MOTIFS_CORBEILLE.map((m) => m.libelle)).toEqual(
      ['Pas intéressé', 'Ne souhaite plus être contacté', 'Doublon', 'Contact incorrect', 'Autre']);
    expect($('modale-corbeille').textContent).toMatch(/Motif \(facultatif\)/);
    expect($('modale-corbeille').querySelector('svg')).not.toBeNull();   // icône SVG, jamais d'emoji
    await cliquer($('motif-ne_plus_contacter'));
    expect($('corbeille-avertissement-refus').textContent).toMatch(/même restauré/);
    await cliquer($('motif-autre'));
    expect($('corbeille-precision')).not.toBeNull();
    await cliquer($('corbeille-annuler'));
    expect(annuler).toHaveBeenCalled();
    expect(confirmer).not.toHaveBeenCalled();
  });
  test('sans motif choisi : la confirmation part avec motif null', async () => {
    const confirmer = jest.fn();
    await monter(<ModaleCorbeille cible={{ id: 'p-1', nom: 'X' }} onConfirmer={confirmer} onAnnuler={() => {}} />);
    await cliquer($('corbeille-confirmer'));
    expect(confirmer).toHaveBeenCalledWith({ motif: null, precision: null });
  });
});

describe('V627 — depuis une conversation et la fiche', () => {
  test('icône corbeille → confirmation → POST (motif) → annonce « Prospect déplacé dans la corbeille »', async () => {
    servir([conversation(1)]);
    await monter(<ProspectsSection API="/api" />);
    await cliquer($('conversation-ligne'));
    expect($('conversation-corbeille').getAttribute('aria-label')).toBe('Mettre à la corbeille');
    await cliquer($('conversation-corbeille'));
    expect($('corbeille-nom').textContent).toBe('Studio TEST V627 1');
    expect(axios.post.mock.calls.filter((c) => /corbeille/.test(c[0]))).toHaveLength(0);   // rien avant confirmation
    await cliquer($('motif-pas_interesse'));
    await cliquer($('corbeille-confirmer'));
    expect(axios.post).toHaveBeenCalledWith('/api/partner-prospects/p-1/corbeille', { motif: 'pas_interesse', precision: null });
    expect($('modale-corbeille')).toBeNull();
    expect($('annonce-corbeille').textContent).toMatch(/Prospect déplacé dans la corbeille/);
    expect(mockReessayer).toHaveBeenCalledWith('prospects');
    expect(mockReessayer).toHaveBeenCalledWith('reponses');
  });

  test('depuis la fiche (même panneau) : icône dans l’en-tête, la fiche se referme après', async () => {
    servir([conversation(2)]);
    axios.get.mockImplementation((url) => Promise.resolve({ data: url === '/api/partner-prospects/p-2'
      ? { id: 'p-2', organisation_name: 'Studio TEST V627 2', category: 'association', status: 'repondu' } : {} }));
    await monter(<ProspectsSection API="/api" />);
    await cliquer($('conversation-ligne'));
    await cliquer($('voir-fiche'));
    expect($('fiche-prospect')).not.toBeNull();
    await cliquer($('fiche-corbeille'));
    await cliquer($('corbeille-confirmer'));
    expect(axios.post).toHaveBeenCalledWith('/api/partner-prospects/p-2/corbeille', { motif: null, precision: null });
    expect($('fiche-prospect')).toBeNull();
  });

  test('refus du serveur : la fenêtre reste ouverte avec le message, rien n’est perdu', async () => {
    servir([conversation(3)]);
    axios.post.mockImplementation(() => Promise.reject({ response: { status: 409, data: { detail: 'Ce prospect est déjà dans la corbeille' } } }));
    await monter(<ProspectsSection API="/api" />);
    await cliquer($('conversation-ligne'));
    await cliquer($('conversation-corbeille'));
    await cliquer($('corbeille-confirmer'));
    expect($('corbeille-erreur').textContent).toMatch(/déjà dans la corbeille/);
    expect($('annonce-corbeille')).toBeNull();
  });

  test('un prospect en corbeille qui a ÉCRIT reste visible, avec le badge « Corbeille » et sans 2e corbeille', async () => {
    servir([conversation(4, { corbeille: true, non_lues: 1 })]);
    await monter(<ProspectsSection API="/api" />);
    expect($('conversation-dans-corbeille').textContent).toBe('Corbeille');
    await cliquer($('conversation-ligne'));
    expect($('conversation-corbeille')).toBeNull();
  });
});

describe('V627 — relances : un prospect en corbeille est « stoppé »', () => {
  const action = { id: 'a1', prospect_ids: ['p-sans-ref'], prospect_uuids: ['p-sans-ref'], channel: 'email', statut: 'pret',
                   execution_type: 'AUTO', recipient_key: 'K' };
  test('corbeille / refus durable → état stoppé avec le bon motif ; fiche retrouvée par son id', () => {
    const corb = lignesRelances([action], { etat: 'approuvee' }, [], [{ id: 'p-sans-ref', corbeille: true }], Date.now())[0];
    expect(corb.etat).toBe(ETATS.STOPPE);
    expect(corb.motifArret).toBe('Prospect dans la corbeille');
    const refus = lignesRelances([action], { etat: 'approuvee' }, [], [{ id: 'p-sans-ref', ne_plus_contacter: { at: 'x' } }], Date.now())[0];
    expect(refus.motifArret).toBe('Ne souhaite plus être contacté');
    const actif = ligneRelance(action, { etat: 'approuvee' }, null, { 'p-sans-ref': { id: 'p-sans-ref' } }, Date.now());
    expect(actif.etat).not.toBe(ETATS.STOPPE);
  });
});

/**
 * RÉACTIVATION 3B — la modale de campagne :
 *  - propose les six segments de réactivation (clés IDENTIQUES au serveur) avec
 *    les comptes V363, sans rien ajouter au panier ;
 *  - un clic bascule la clé dans `newCampaign.targetCategories` (envoyé au serveur,
 *    résolu au lancement) ; un second clic la retire ;
 *  - l'estimation et l'avertissement « canal e-mail » s'affichent ;
 *  - le bouton Suivant s'ouvre avec des segments seuls (sans panier).
 */
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import axios from 'axios';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock('../../CloudinaryUploadButton', () => () => null);

const CampaignModal = require('../CampaignModal').default;
const { R3_SEGMENTS } = require('../CampaignModal');

const CLES = ['essai_non_converti', 'essai_presence_inconnue', 'essai_non_reserve', 'ancien_participant', 'ancien_abonne', 'recent_non_abonne'];
const ETIQUETTES = { demarchable_whatsapp: 12, abonne_actif: 3, essai_non_converti: 3, essai_presence_inconnue: 2, essai_non_reserve: 8,
  ancien_participant: 26, ancien_abonne: 10, recent_non_abonne: 25 };

let racine; let conteneur; let dernier;

function Harnais({ channels }) {
  const [newCampaign, setNewCampaign] = useState({
    name: 'Reprise hiver', message: 'On reprend !', mediaUrl: '', mediaFormat: '16:9', targetType: 'all', selectedContacts: [],
    channels: channels || { whatsapp: false, email: false, internal: true }, targetGroupId: 'community', scheduleSlots: [], targetCategories: [],
  });
  const [selectedRecipients, setSelectedRecipients] = useState([]);
  dernier = newCampaign;
  return (
    <CampaignModal isOpen onClose={() => {}} newCampaign={newCampaign} setNewCampaign={setNewCampaign}
      selectedRecipients={selectedRecipients} setSelectedRecipients={setSelectedRecipients}
      activeConversations={[]} showConversationDropdown={false} setShowConversationDropdown={() => {}}
      conversationSearch="" setConversationSearch={() => {}} API="http://api.test" aiConfig={{}}
      createCampaign={() => {}} cancelEditCampaign={() => {}} showCampaignToast={() => {}}
      addScheduleSlot={() => {}} removeScheduleSlot={() => {}} updateScheduleSlot={() => {}} coachEmail="coach@test.ch" />
  );
}

beforeEach(() => {
  axios.get.mockImplementation((url) => {
    if (url.endsWith('/contacts/segments')) return Promise.resolve({ data: { etiquettes: ETIQUETTES } });
    if (url.includes('/contacts/segment/')) return Promise.resolve({ data: { contacts: [], adressables: 0, sans_identifiant: 0 } });
    return Promise.resolve({ data: [] });
  });
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
});
afterEach(() => { act(() => racine.unmount()); conteneur.remove(); });

async function monterEtape2(channels) {
  await act(async () => { racine.render(<Harnais channels={channels} />); });
  const suivant = [...conteneur.querySelectorAll('button')].find((b) => /Suivant/.test(b.textContent));
  await act(async () => { suivant.click(); });
  await act(async () => {});           // chargement des segments
}

test('les six segments, clés identiques au serveur, avec les comptes V363', async () => {
  expect(R3_SEGMENTS.map((s) => s.cle)).toEqual(CLES);
  await monterEtape2();
  const bloc = conteneur.querySelector('[data-testid="r3-segments"]');
  expect(bloc).not.toBeNull();
  CLES.forEach((k) => {
    const b = conteneur.querySelector(`[data-testid="r3-segment-${k}"]`);
    expect(b).not.toBeNull();
    expect(b.textContent).toMatch(new RegExp(`\\(${ETIQUETTES[k]}\\)`));
    expect(b.getAttribute('aria-pressed')).toBe('false');
  });
  expect(bloc.textContent).toMatch(/Résolu au moment de l'envoi/);
});

test('un clic bascule la clé dans targetCategories (rien dans le panier), un second la retire', async () => {
  await monterEtape2();
  const b = conteneur.querySelector('[data-testid="r3-segment-essai_non_converti"]');
  await act(async () => { b.click(); });
  expect(dernier.targetCategories).toEqual(['essai_non_converti']);
  expect(conteneur.querySelector('[data-testid="r3-segment-essai_non_converti"]').getAttribute('aria-pressed')).toBe('true');
  await act(async () => { conteneur.querySelector('[data-testid="r3-segment-ancien_abonne"]').click(); });
  expect(dernier.targetCategories).toEqual(['essai_non_converti', 'ancien_abonne']);
  // Estimation = somme des comptes, liste exacte renvoyée à l'aperçu serveur.
  expect(conteneur.textContent).toMatch(/2 segments de réactivation — 13 personnes estimées, liste exacte à l'aperçu/);
  // Aucun appel à /contacts/segment/<cle> : rien n'est déplié dans le panier.
  expect(axios.get.mock.calls.filter(([u]) => /\/contacts\/segment\/(essai|ancien|recent)/.test(u))).toHaveLength(0);
  await act(async () => { conteneur.querySelector('[data-testid="r3-segment-essai_non_converti"]').click(); });
  expect(dernier.targetCategories).toEqual(['ancien_abonne']);
});

test('sans canal e-mail : avertissement ; avec : aucun', async () => {
  await monterEtape2({ whatsapp: false, email: false, internal: true });
  await act(async () => { conteneur.querySelector('[data-testid="r3-segment-ancien_abonne"]').click(); });
  expect(conteneur.textContent).toMatch(/Active le canal e-mail/);
  act(() => racine.unmount());
  conteneur = document.createElement('div'); document.body.appendChild(conteneur); racine = createRoot(conteneur);
  await monterEtape2({ whatsapp: false, email: true, internal: false });
  await act(async () => { conteneur.querySelector('[data-testid="r3-segment-ancien_abonne"]').click(); });
  expect(conteneur.textContent).not.toMatch(/Active le canal e-mail/);
});

test('segments seuls (panier vide, aucun canal) : « Suivant » est ouvert', async () => {
  await monterEtape2();
  await act(async () => { conteneur.querySelector('[data-testid="r3-segment-recent_non_abonne"]').click(); });
  const suivant = [...conteneur.querySelectorAll('button')].find((b) => /Suivant/.test(b.textContent));
  expect(suivant.disabled).toBe(false);
});

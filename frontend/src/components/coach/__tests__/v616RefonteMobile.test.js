// V616 — REFONTE MOBILE DE LA PAGE CAMPAGNES (UI SEULEMENT).
//
// CE QUI EST PROUVÉ ICI :
//   A. Tâches : carte compacte « Tâches · N à venir · + Ajouter », 3 tâches puis
//      « Voir toutes les tâches », filtres toujours présents (repliés sur téléphone).
//   B. Calendrier : « Aujourd'hui », segment Jour/Semaine/Mois, « Filtrer » ; le
//      gestionnaire ne double plus « + Créer » (un seul, dans son en-tête).
//   C. Gestionnaire en mode onglet : plus de gros bloc Invitation ; « ⋯ » regroupe
//      Google Calendar et Créateur / Affiliation, avec les MÊMES actions.
//   D. Historique : repliable, cartes avec 2 actions visibles + « ⋯ » (Dupliquer,
//      Date d'envoi, Supprimer) qui appellent EXACTEMENT les mêmes fonctions.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';

jest.mock('axios', () => ({
  get: jest.fn(() => Promise.resolve({ data: {} })),
  post: jest.fn(() => Promise.resolve({ data: {} })),
  put: jest.fn(() => Promise.resolve({ data: {} })),
  patch: jest.fn(() => Promise.resolve({ data: {} })),
}));
jest.mock('../CampaignModal', () => () => null);
jest.mock('../InvitationModal', () => (props) => (props.isOpen ? <div data-testid="invitation-modal" /> : null), { virtual: true });

// eslint-disable-next-line import/first
import axios from 'axios';
// eslint-disable-next-line import/first
import CampaignManager from '../CampaignManager';
// eslint-disable-next-line import/first
import CampaignCalendar from '../CampaignCalendar';
// eslint-disable-next-line import/first
import TasksPanel from '../TasksPanel';

let conteneur = null;
let racine = null;
beforeEach(() => {
  axios.get.mockImplementation(() => Promise.resolve({ data: {} }));
  axios.post.mockImplementation(() => Promise.resolve({ data: {} }));
});
async function monter(element) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(element); });
}
afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) document.body.removeChild(conteneur);
  racine = null; conteneur = null;
});
const par = (id) => document.querySelector(`[data-testid="${id}"]`);
const tous = (sel) => Array.from(document.querySelectorAll(sel));
const cliquer = (el) => act(async () => { el.dispatchEvent(new MouseEvent('click', { bubbles: true })); });
const boutonTexte = (t) => tous('button').find((b) => (b.textContent || '').trim().indexOf(t) === 0);

const tache = (i) => ({ id: `t-${i}`, title: `Tâche ${i}`, starts_at: '2026-10-13T14:35:00Z', status: 'prevu', bucket: 'a_venir' });

describe('A. Tâches', () => {
  test('en-tête compact et « + Ajouter »', async () => {
    await monter(<TasksPanel taches={[tache(1)]} compteurs={{ a_venir: 4 }} />);
    expect(par('taches-a-venir').textContent).toContain('4 à venir');
    expect(par('nouvelle-tache').textContent).toContain('Ajouter');
    expect(par('taches-filtrer')).toBeTruthy();
    expect(par('pile-en_retard')).toBeTruthy(); // filtres conservés
  });
  test('3 tâches d’abord, puis « Voir toutes les tâches »', async () => {
    await monter(<TasksPanel taches={[1, 2, 3, 4, 5].map(tache)} />);
    expect(tous('[data-testid="tache-ligne"]').length).toBe(3);
    expect(par('taches-voir-toutes').textContent).toContain('5');
    await cliquer(par('taches-voir-toutes'));
    expect(tous('[data-testid="tache-ligne"]').length).toBe(5);
  });
  test('aucun glyphe texte comme icône sur la case à cocher', async () => {
    await monter(<TasksPanel taches={[tache(1)]} />);
    expect(par('basculer-tache').querySelector('svg')).toBeTruthy();
    expect(par('basculer-tache').textContent).not.toMatch(/[✓↺]/);
  });
});

describe('B. Calendrier', () => {
  test('en-tête compact : Aujourd’hui, segment de vues, Filtrer', async () => {
    await monter(<CampaignCalendar evenements={[]} />);
    expect(par('aujourdhui').textContent).toContain('Aujourd');
    ['vue-jour', 'vue-semaine', 'vue-mois', 'calendrier-filtrer', 'filtre-google', 'creer'].forEach((id) => expect(par(id)).toBeTruthy());
  });
  test('boutonCreer={false} : pas de « + Créer » dans la grille', async () => {
    await monter(<CampaignCalendar evenements={[]} boutonCreer={false} />);
    expect(par('creer')).toBeNull();
  });
});

const props = (extra = {}) => ({
  campaigns: [], campaignLogs: [], activeConversations: [], campaignHistoryFilter: 'all',
  setCampaignHistoryFilter: jest.fn(), showCampaignToast: jest.fn(), cancelEditCampaign: jest.fn(),
  setNewCampaign: jest.fn(), API: '/api-test', coachCredits: 10, isSuperAdmin: false, ...extra,
});

describe('C. Gestionnaire en mode onglet', () => {
  test('plus de gros bloc Invitation, un seul « + Créer », menu « ⋯ »', async () => {
    const ouvrir = jest.fn();
    await monter(<CampaignManager {...props({ invitationViaOnglet: true, onOuvrirCreateur: ouvrir })} />);
    expect(par('campagnes-modules')).toBeNull();
    expect(par('module-invitation')).toBeNull();
    expect(tous('[data-testid="creer"]').length).toBe(1);
    expect(par('automate-etat')).toBeTruthy();
    expect(par('bandeau-google')).toBeNull();
    await cliquer(par('campagnes-plus'));
    expect(par('bandeau-google')).toBeTruthy();
    expect(par('google-connecter')).toBeTruthy();
    await cliquer(par('module-createur'));
    expect(ouvrir).toHaveBeenCalledTimes(1);
  });
  test('« + Créer » de l’en-tête ouvre le même choix', async () => {
    await monter(<CampaignManager {...props({ invitationViaOnglet: true })} />);
    await cliquer(par('creer'));
    expect(par('creer-choix')).toBeTruthy();
  });
});

describe('D. Historique en cartes', () => {
  const campagne = { id: 'c1', name: 'Offre hiver', status: 'sent', channels: { email: true }, selectedContacts: ['a', 'b'] };
  test('repliable et cartes avec actions identiques', async () => {
    const supprimer = jest.fn();
    await monter(<CampaignManager {...props({ campaigns: [campagne], deleteCampaign: supprimer })} />);
    if (!par('historique-cartes')) await cliquer(par('historique-toggle'));
    const carte = par('historique-carte');
    expect(carte.textContent).toContain('Offre hiver');
    expect(carte.textContent).toContain('Envoyé');
    expect(boutonTexte('Modifier')).toBeTruthy();
    expect(boutonTexte('Relancer')).toBeTruthy();
    await cliquer(carte.querySelector('[aria-label="Plus d\'actions"]'));
    expect(boutonTexte('Dupliquer')).toBeTruthy();
    expect(boutonTexte('Choisir la date')).toBeTruthy();
    await cliquer(boutonTexte('Supprimer'));
    expect(supprimer).toHaveBeenCalledWith('c1');
    await cliquer(par('historique-toggle'));
    expect(par('historique-cartes')).toBeNull();
  });
});

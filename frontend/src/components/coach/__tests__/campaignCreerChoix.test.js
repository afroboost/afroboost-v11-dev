// INVITATION — LE POINT D'ENTRÉE « + Créer » DE LA PAGE CAMPAGNES.
//
// CE QUI EST PROUVÉ ICI :
//   A. NON-RÉGRESSION — « + Créer » → « Campagne » ouvre EXACTEMENT ce que
//      « + Créer » ouvrait avant : la même modale de campagne, préremplie à la
//      date du jour, après la même vérification de crédits (même toast) ;
//      un clic sur un JOUR ouvre toujours directement la campagne, sans choix ;
//      le calendrier SANS `onCreer` se comporte comme avant.
//   B. « + Créer » → « Invitation » ouvre InvitationModal (isOpen, API,
//      dateInitiale) ; onClose la ferme.
//   C. Échap / clic extérieur ferment le choix sans rien ouvrir.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';

jest.mock('axios', () => ({
  get: jest.fn(() => Promise.resolve({ data: {} })),
  post: jest.fn(() => Promise.resolve({ data: {} })),
  put: jest.fn(() => Promise.resolve({ data: {} })),
}));
jest.mock('../TasksPanel', () => () => null);

/* La modale de campagne est remplacée par un témoin qui expose ses props :
   on vérifie qu'elle reçoit isOpen=true et la date du jour, comme avant. */
const mockCampaignModal = jest.fn();
jest.mock('../CampaignModal', () => (props) => {
  mockCampaignModal(props);
  if (!props.isOpen) return null;
  return (
    <div data-testid="campaign-modal" data-date={props.preSelectedDate || ''}>
      <button type="button" data-testid="campaign-modal-fermer" onClick={props.onClose}>x</button>
    </div>
  );
});

/* InvitationModal est écrit en parallèle : on le simule ici. */
const mockInvitationModal = jest.fn();
jest.mock('../InvitationModal', () => (props) => {
  mockInvitationModal(props);
  if (!props.isOpen) return null;
  return (
    <div data-testid="invitation-modal" data-date={props.dateInitiale || ''} data-api={props.API}>
      <button type="button" data-testid="invitation-fermer" onClick={props.onClose}>x</button>
    </div>
  );
}, { virtual: true });

// eslint-disable-next-line import/first
import axios from 'axios';
// eslint-disable-next-line import/first
import CampaignManager from '../CampaignManager';
// eslint-disable-next-line import/first
import CampaignCalendar from '../CampaignCalendar';

let conteneur = null;
let racine = null;

/* CRA active `resetMocks` : les implémentations sont remises à zéro avant
   chaque test, on les repose donc ici. */
beforeEach(() => {
  axios.get.mockImplementation(() => Promise.resolve({ data: {} }));
  axios.post.mockImplementation(() => Promise.resolve({ data: {} }));
  axios.put.mockImplementation(() => Promise.resolve({ data: {} }));
});

async function monter(element) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(element); });
  return conteneur;
}

afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) document.body.removeChild(conteneur);
  racine = null; conteneur = null;
  mockCampaignModal.mockClear();
  mockInvitationModal.mockClear();
});

const par = (id) => document.querySelector(`[data-testid="${id}"]`);
const cliquer = (el) => act(async () => {
  el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
});
const touche = (key) => act(async () => {
  document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
});

const cle2 = (n) => String(n).padStart(2, '0');
const AUJ = new Date();
const ISO_AUJ = `${AUJ.getFullYear()}-${cle2(AUJ.getMonth() + 1)}-${cle2(AUJ.getDate())}`;

function propsManager(extra = {}) {
  return {
    campaigns: [],
    campaignLogs: [],
    activeConversations: [],
    campaignHistoryFilter: 'all',
    setCampaignHistoryFilter: jest.fn(),
    showCampaignToast: jest.fn(),
    cancelEditCampaign: jest.fn(),
    setNewCampaign: jest.fn(),
    API: '/api-test',
    coachCredits: 10,
    isSuperAdmin: false,
    ...extra,
  };
}

describe('A — non-régression du chemin Campagne', () => {
  test('« + Créer » ouvre le choix, sans ouvrir aucune modale', async () => {
    await monter(<CampaignManager {...propsManager()} />);
    await cliquer(par('creer'));
    expect(par('creer-choix')).not.toBeNull();
    expect(par('creer-campagne')).not.toBeNull();
    expect(par('creer-invitation')).not.toBeNull();
    expect(par('campaign-modal')).toBeNull();
    expect(par('invitation-modal')).toBeNull();
  });

  test('« Campagne » ouvre la modale de campagne à la date du jour (comme avant)', async () => {
    const p = propsManager();
    await monter(<CampaignManager {...p} />);
    await cliquer(par('creer'));
    await cliquer(par('creer-campagne'));
    expect(par('creer-choix')).toBeNull();
    const modale = par('campaign-modal');
    expect(modale).not.toBeNull();
    expect(modale.getAttribute('data-date')).toBe(ISO_AUJ);
    // openNewCampaign réinitialise le formulaire, comme avant.
    expect(p.cancelEditCampaign).toHaveBeenCalled();
    expect(par('invitation-modal')).toBeNull();
  });

  test('crédits insuffisants : « Campagne » est bloqué par le MÊME toast', async () => {
    const p = propsManager({ coachCredits: 0 });
    await monter(<CampaignManager {...p} />);
    await cliquer(par('creer'));
    await cliquer(par('creer-campagne'));
    expect(p.showCampaignToast).toHaveBeenCalledWith(
      '🔒 Crédits insuffisants. Rechargez votre pack pour créer des campagnes.', 'error');
    expect(par('campaign-modal')).toBeNull();
  });

  test('clic sur un JOUR : campagne directe, pas de choix', async () => {
    await monter(<CampaignManager {...propsManager()} />);
    await cliquer(par(`jour-${ISO_AUJ}`));
    expect(par('creer-choix')).toBeNull();
    const modale = par('campaign-modal');
    expect(modale).not.toBeNull();
    expect(modale.getAttribute('data-date')).toBe(ISO_AUJ);
  });

  test('CampaignCalendar SANS onCreer : « + Créer » appelle onDayClick(aujourd\'hui)', async () => {
    const onDayClick = jest.fn();
    await monter(<CampaignCalendar evenements={[]} onDayClick={onDayClick} />);
    await cliquer(par('creer'));
    expect(onDayClick).toHaveBeenCalledTimes(1);
    expect(onDayClick).toHaveBeenCalledWith(ISO_AUJ);
  });

  test('CampaignCalendar AVEC onCreer : « + Créer » appelle onCreer, pas onDayClick ; un jour appelle onDayClick', async () => {
    const onDayClick = jest.fn();
    const onCreer = jest.fn();
    await monter(<CampaignCalendar evenements={[]} onDayClick={onDayClick} onCreer={onCreer} />);
    await cliquer(par('creer'));
    expect(onCreer).toHaveBeenCalledWith(ISO_AUJ);
    expect(onDayClick).not.toHaveBeenCalled();
    await cliquer(par(`jour-${ISO_AUJ}`));
    expect(onDayClick).toHaveBeenCalledWith(ISO_AUJ);
    expect(onCreer).toHaveBeenCalledTimes(1);
  });
});

describe('B — chemin Invitation', () => {
  test('« Invitation » ouvre InvitationModal avec isOpen, API et dateInitiale ; onClose la ferme', async () => {
    await monter(<CampaignManager {...propsManager()} />);
    await cliquer(par('creer'));
    await cliquer(par('creer-invitation'));
    expect(par('creer-choix')).toBeNull();
    expect(par('campaign-modal')).toBeNull();
    const modale = par('invitation-modal');
    expect(modale).not.toBeNull();
    const derniers = mockInvitationModal.mock.calls[mockInvitationModal.mock.calls.length - 1][0];
    expect(derniers.isOpen).toBe(true);
    expect(derniers.API).toBe('/api-test');
    expect(derniers.dateInitiale).toBe(ISO_AUJ);
    expect(typeof derniers.onClose).toBe('function');
    await cliquer(par('invitation-fermer'));
    expect(par('invitation-modal')).toBeNull();
  });

  test('« Invitation » ne vérifie PAS les crédits de campagne et n\'affiche aucun toast', async () => {
    const p = propsManager({ coachCredits: 0 });
    await monter(<CampaignManager {...p} />);
    await cliquer(par('creer'));
    await cliquer(par('creer-invitation'));
    expect(par('invitation-modal')).not.toBeNull();
    expect(p.showCampaignToast).not.toHaveBeenCalled();
  });
});

describe('C — fermeture du choix', () => {
  test('Échap ferme le choix sans rien ouvrir', async () => {
    await monter(<CampaignManager {...propsManager()} />);
    await cliquer(par('creer'));
    expect(par('creer-choix')).not.toBeNull();
    await touche('Escape');
    expect(par('creer-choix')).toBeNull();
    expect(par('campaign-modal')).toBeNull();
    expect(par('invitation-modal')).toBeNull();
  });

  test('clic extérieur ferme le choix sans rien ouvrir', async () => {
    await monter(<CampaignManager {...propsManager()} />);
    await cliquer(par('creer'));
    await cliquer(par('creer-choix-fond'));
    expect(par('creer-choix')).toBeNull();
    expect(par('campaign-modal')).toBeNull();
    expect(par('invitation-modal')).toBeNull();
  });

  test('un clic DANS le choix (hors boutons) ne le ferme pas', async () => {
    await monter(<CampaignManager {...propsManager()} />);
    await cliquer(par('creer'));
    await cliquer(par('creer-choix'));
    expect(par('creer-choix')).not.toBeNull();
  });

  test('aucune couleur de marque codée en dur dans le choix', async () => {
    await monter(<CampaignManager {...propsManager()} />);
    await cliquer(par('creer'));
    const html = par('creer-choix-fond').outerHTML;
    expect(html).not.toMatch(/#D91CD2(?!\))/i);
    expect(html).not.toMatch(/#(a855f7|8B5CF6|9333ea|7c3aed)/i);
  });
});

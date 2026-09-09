/**
 * SESSION ABONNÉE PERSISTANTE — « je me connecte une fois, puis on me reconnaît ».
 *
 * CE QUE CE BANC PROUVE. La session existait déjà (LOT B3-S1 : jeton de 30 jours,
 * révocable en base). Ce qui manquait était la PORTE : `start_url` de la PWA vaut
 * « / », et rien ne ramenait l'abonné chez lui — il devait retrouver son code dans
 * un vieil e-mail. On vérifie donc les deux moitiés : la session tient, ET elle
 * rouvre l'espace toute seule au lancement.
 *
 * Aucun réseau : `axios` est un mouchard. Aucun envoi, aucune base.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import SubscriberSpace from '../SubscriberSpace';
import {
  ESPACE_CLE, ESPACE_CLE_RETOUR, lireSession, sessionPourEspace,
  ecrireSession, oublierSession, urlDeLaSession,
} from '../../utils/espaceSession';

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('axios', () => ({
  __esModule: true,
  default: {
    get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn(),
    interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } },
  },
}));
jest.mock('../ConditionsParticipation', () => () => null);
jest.mock('../ConversionApresEssai', () => () => null);
jest.mock('../SubscriberOnboarding', () => () => null);
jest.mock('../SubscriberCockpit', () => () => null);
jest.mock('../SvgIcon', () => () => null);
jest.mock('../InvitationTemoignage', () => ({
  __esModule: true, default: () => null, enRepos: () => false,
}));
jest.mock('../Publications', () => ({ PublishModal: () => null }));
jest.mock('qrcode.react', () => ({ QRCodeSVG: () => null }));
jest.mock('../ui/dialog', () => ({
  Dialog: ({ children }) => children,
  DialogContent: ({ children }) => children,
  DialogTitle: ({ children }) => children,
}));

const CODE = 'AFR-SESSION1';
const AUTRE = 'AFR-SESSION2';
const DANS_30_J = new Date(Date.now() + 30 * 86400000).toISOString();
const HIER = new Date(Date.now() - 86400000).toISOString();

const espaceComplet = {
  subscriber: { name: 'Ana', code: CODE, whatsapp: '+41760000000' },
  subscription: { id: 's1', code: CODE, offer_name: 'PULSE', total_sessions: 10,
                  used_sessions: 6, remaining_sessions: 4 },
  coach: { name: 'Afroboost' }, upcoming_courses: [], reservations: [],
};

let conteneur;

async function monter(code = CODE) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  await act(async () => {
    createRoot(conteneur).render(<SubscriberSpace accessCode={code} />);
  });
}

const parId = (id) => conteneur.querySelector(`[data-testid="${id}"]`);

beforeEach(() => {
  jest.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  document.body.innerHTML = '';
  axios.get.mockResolvedValue({ data: espaceComplet });
  axios.post.mockResolvedValue({ data: { success: true } });
});

// ═══════════════════════════════════════════════════════════ A / B / K
describe('A, B, K — première connexion, puis plus rien à saisir', () => {
  test('A. sans session, le code est demandé et AUCUNE donnée n’est chargée', async () => {
    await monter();
    expect(parId('espace-identification')).toBeTruthy();
    expect(axios.get).not.toHaveBeenCalled();
  });

  test('B. avec une session valide, l’espace s’ouvre sans rien redemander', async () => {
    ecrireSession(CODE, '', 'jeton.valide', DANS_30_J);
    await monter();
    expect(parId('espace-identification')).toBeFalsy();
    expect(axios.get).toHaveBeenCalled();
  });

  test('K. aucun code d’accès n’est stocké en clair comme secret réutilisable', () => {
    ecrireSession(CODE, '', 'jeton.valide', DANS_30_J);
    const brut = window.localStorage.getItem(ESPACE_CLE);
    // Le code est là pour savoir QUEL espace ouvrir — il n'ouvre rien seul
    // depuis B3-S1.3. Ce qui ne doit PAS y être : un mot de passe, un OTP.
    expect(brut).toContain('jeton.valide');
    expect(brut).not.toMatch(/otp|password|mot_?de_?passe/i);
    // Et la seule clé utilisée est celle-là : pas de seconde copie ailleurs.
    const cles = Object.keys(window.localStorage);
    expect(cles.filter((c) => c.indexOf('espace') !== -1)).toEqual([ESPACE_CLE]);
  });
});

// ═══════════════════════════════════════════════════════════ C / D
describe('C, D — fermer, rouvrir, redémarrer', () => {
  test('C. la session survit à un remontage complet du composant', async () => {
    ecrireSession(CODE, '', 'jeton.valide', DANS_30_J);
    await monter();
    expect(parId('espace-identification')).toBeFalsy();
    document.body.innerHTML = '';
    await monter();                       // = fermer puis rouvrir la PWA
    expect(parId('espace-identification')).toBeFalsy();
  });

  test('D. elle vit en localStorage, donc elle survit au redémarrage', () => {
    ecrireSession(CODE, '', 'jeton.valide', DANS_30_J);
    // sessionStorage meurt avec l'onglet ; localStorage non. C'est précisément
    // pour cela que la session n'y est PAS.
    expect(window.sessionStorage.getItem(ESPACE_CLE)).toBeNull();
    expect(lireSession()).toBeTruthy();
  });

  test('D2. une session périmée n’est pas une session', () => {
    ecrireSession(CODE, '', 'jeton.vieux', HIER);
    expect(lireSession()).toBeNull();
  });
});

// ═══════════════════════════════════════════════════════════ G / H
describe('G, H — déconnexion et révocation', () => {
  test('G. « Se déconnecter » révoque côté serveur AVANT d’oublier le jeton', async () => {
    ecrireSession(CODE, '', 'jeton.valide', DANS_30_J);
    const assign = jest.fn();
    delete window.location;
    window.location = { assign, pathname: `/espace/${CODE}`, search: '', origin: 'https://afroboost.com' };
    await monter();
    await act(async () => { parId('espace-deconnexion').click(); });
    const appels = axios.post.mock.calls.map((c) => c[0]);
    expect(appels.some((u) => String(u).indexOf('/subscriber/session/revoke') !== -1)).toBe(true);
    expect(window.localStorage.getItem(ESPACE_CLE)).toBeNull();
    expect(assign).toHaveBeenCalledWith('/');
  });

  test('G2. après déconnexion, le code est redemandé', async () => {
    ecrireSession(CODE, '', 'jeton.valide', DANS_30_J);
    oublierSession();
    await monter();
    expect(parId('espace-identification')).toBeTruthy();
  });

  test('H. oublier la session efface AUSSI le pense-bête du retour automatique', () => {
    ecrireSession(CODE, '', 'jeton.valide', DANS_30_J);
    window.sessionStorage.setItem(ESPACE_CLE_RETOUR, '1');
    oublierSession();
    expect(window.sessionStorage.getItem(ESPACE_CLE_RETOUR)).toBeNull();
  });
});

// ═══════════════════════════════════════════════════════════ I
describe('I — deux abonnés sur le même appareil', () => {
  test('I. la session de l’un n’ouvre JAMAIS l’espace de l’autre', async () => {
    ecrireSession(CODE, '', 'jeton.de.ana', DANS_30_J);
    expect(sessionPourEspace(AUTRE, '')).toBeNull();
    await monter(AUTRE);
    expect(parId('espace-identification')).toBeTruthy();
    expect(axios.get).not.toHaveBeenCalled();
  });

  test('I2. un membre de groupe ne prend pas la place d’un autre', () => {
    ecrireSession(CODE, 'ana', 'jeton.de.ana', DANS_30_J);
    expect(sessionPourEspace(CODE, 'bob')).toBeNull();
    expect(sessionPourEspace(CODE, 'ana')).toBeTruthy();
  });

  test('I3. se connecter avec un autre compte REMPLACE la session précédente', () => {
    ecrireSession(CODE, '', 'jeton.de.ana', DANS_30_J);
    ecrireSession(AUTRE, '', 'jeton.de.bob', DANS_30_J);
    expect(sessionPourEspace(CODE, '')).toBeNull();
    expect(sessionPourEspace(AUTRE, '').token).toBe('jeton.de.bob');
  });
});

// ═══════════════════════════════════════════════════════════ renouvellement
describe('Renouvellement glissant', () => {
  test('le jeton renvoyé par le serveur remplace l’ancien', async () => {
    ecrireSession(CODE, '', 'jeton.bientot.perime', DANS_30_J);
    const plusTard = new Date(Date.now() + 30 * 86400000).toISOString();
    axios.get.mockResolvedValue({
      data: { ...espaceComplet, espace_token: 'jeton.neuf', espace_token_expires_at: plusTard },
    });
    await monter();
    expect(lireSession().token).toBe('jeton.neuf');
    // ET SURTOUT : UNE SEULE lecture de l'espace. Ranger le jeton neuf ne doit
    // pas relancer le chargement — c'est la boucle d'appels que ce dépôt
    // connaît déjà (règle absolue du CLAUDE.md). On compte les appels à CETTE
    // route, pas tous les GET du composant.
    const lectures = axios.get.mock.calls
      .map((c) => String(c[0]))
      .filter((u) => u.indexOf('/subscriber/space/') !== -1);
    expect(lectures).toHaveLength(1);
  });

  test('sans renouvellement, l’ancien jeton reste en place', async () => {
    ecrireSession(CODE, '', 'jeton.valide', DANS_30_J);
    await monter();
    expect(lireSession().token).toBe('jeton.valide');
  });
});

// ═══════════════════════════════════════════════════════════ E / F / J
describe('E, F, J — l’adresse de l’espace', () => {
  test('E/F. la session sait vers quelle page ramener', () => {
    ecrireSession(CODE, '', 'jeton.valide', DANS_30_J);
    expect(urlDeLaSession()).toBe(`/espace/${encodeURIComponent(CODE)}`);
  });

  test('J. le membre visé est conservé dans l’adresse', () => {
    ecrireSession(CODE, 'ana', 'jeton.valide', DANS_30_J);
    expect(urlDeLaSession()).toBe(`/espace/${encodeURIComponent(CODE)}?m=ana`);
  });

  test('sans session, aucune adresse — on ne devine pas un espace', () => {
    expect(urlDeLaSession()).toBe('');
  });
});

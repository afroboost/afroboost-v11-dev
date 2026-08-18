/**
 * P0-SOCLE — Contacts : le scenario decrit par le coach.
 *
 *   « Total 0 / Groupes 0 / Contacts 0 / Google 0 + Chargement... »
 *
 * ne doit plus etre possible apres un echec de recuperation.
 *
 * AUCUNE regle metier Contacts V2 n'est testee ni touchee ici : ces tests ne
 * portent QUE sur l'honnetete de l'affichage pendant et apres le chargement.
 *
 * HORS LIGNE, sans dependance ajoutee : rendu via `react-dom/client`, `axios`
 * simule. Aucun reseau, aucune base, aucune donnee de production.
 */

import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import ContactsManager from '../ContactsManager';
import { _reinitialiserConnexions } from '../../../utils/authSession';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const API = '/api';

function jetonValide() {
  const entete = btoa(JSON.stringify({ alg: 'HS256' }));
  const charge = btoa(
    JSON.stringify({ email: 'coach@test.ch', exp: Math.floor(Date.now() / 1000) + 3600 })
  );
  return `${entete}.${charge}.factice`;
}

let conteneur = null;
let racine = null;

beforeEach(() => {
  localStorage.clear();
  _reinitialiserConnexions();
  jest.clearAllMocks();
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
});

afterEach(async () => {
  await act(async () => racine.unmount());
  conteneur.remove();
});

async function rendre() {
  await act(async () => {
    racine.render(<ContactsManager API={API} coachEmail="coach@test.ch" isSuperAdmin />);
  });
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

/** Les quatre pastilles de tete, dans l'ordre Total / Groupes / Contacts / Google. */
function compteurs() {
  return ['total', 'groupes', 'contacts', 'google'].map((nom) => {
    const noeud = conteneur.querySelector(`[data-testid="compteur-${nom}"]`);
    return noeud ? { texte: noeud.textContent.trim(), etat: noeud.getAttribute('data-etat') } : null;
  });
}

/** Reponse reussie du serveur, telle que /contacts/all la renvoie reellement. */
const reponseContacts = (liste) => ({ data: { success: true, contacts: liste } });

function routerAxios(carte) {
  axios.get.mockImplementation((url) => {
    const cle = Object.keys(carte).find((motif) => url.indexOf(motif) !== -1);
    if (!cle) return Promise.resolve({ data: {} });
    const valeur = carte[cle];
    return typeof valeur === 'function' ? valeur() : Promise.resolve(valeur);
  });
}

describe('Contacts — pendant le chargement, aucun chiffre n\'est affirme', () => {
  test('les quatre compteurs affichent « — », jamais « 0 »', async () => {
    localStorage.setItem('afroboost_jwt', jetonValide());
    // Aucune promesse ne se resout : on observe l'ecran EN COURS de chargement.
    routerAxios({
      '/contacts/all': () => new Promise(() => {}),
      '/contact-categories': () => new Promise(() => {}),
      '/google-contacts/status': () => new Promise(() => {}),
    });

    await rendre();

    compteurs().forEach((c) => {
      expect(c).not.toBeNull();
      expect(c.etat).toBe('chargement');
      expect(c.texte).toBe('—');
      expect(c.texte).not.toBe('0');
    });
  });
});

describe('Contacts — apres un echec, « Indisponible / Reessayer », jamais 0', () => {
  test('un 403 sur /contacts/all n\'affiche AUCUN zero', async () => {
    // Session zombie : mode coach conserve, aucun jeton signe. C'est l'etat
    // exact qui produisait « Total 0 / Groupes 0 / Contacts 0 / Google 0 ».
    localStorage.setItem('afroboost_coach_mode', 'true');
    routerAxios({
      '/contacts/all': () => Promise.reject({ response: { status: 403 } }),
      '/contact-categories': { data: { success: true, categories: [] } },
      '/google-contacts/status': { data: { connected: false, configured: true } },
    });

    await rendre();

    compteurs().forEach((c) => {
      expect(c.texte).not.toBe('0');
      expect(['erreur', 'session']).toContain(c.etat);
    });

    // Et l'echec est DIT, avec une issue.
    const bandeau = conteneur.querySelector('[data-testid="erreur-contacts-contacts"]');
    expect(bandeau).not.toBeNull();
    expect(bandeau.querySelector('[data-testid="bouton-reessayer"]')).not.toBeNull();
  });

  test('la route protegee n\'est meme PAS appelee sans preuve signee', async () => {
    localStorage.setItem('afroboost_coach_mode', 'true');
    routerAxios({
      '/contacts/all': () => Promise.reject({ response: { status: 403 } }),
      '/contact-categories': { data: { success: true, categories: [] } },
      '/google-contacts/status': { data: { connected: false } },
    });

    await rendre();

    const urls = axios.get.mock.calls.map((appel) => appel[0]);
    // /contacts/all est JWT-strict (403 mesure en production) : inutile de la
    // lancer sans jeton. Les deux autres, elles, partent normalement.
    expect(urls.some((u) => u.indexOf('/contacts/all') !== -1)).toBe(false);
    expect(urls.some((u) => u.indexOf('/contact-categories') !== -1)).toBe(true);
    expect(urls.some((u) => u.indexOf('/google-contacts/status') !== -1)).toBe(true);
  });

  test('un 500 laisse les compteurs muets et propose Reessayer', async () => {
    localStorage.setItem('afroboost_jwt', jetonValide());
    routerAxios({
      '/contacts/all': () => Promise.reject({ response: { status: 500 } }),
      '/contact-categories': { data: { success: true, categories: [] } },
      '/google-contacts/status': { data: { connected: false } },
    });

    await rendre();

    compteurs().forEach((c) => expect(c.texte).not.toBe('0'));
    expect(conteneur.querySelector('[data-testid="bouton-reessayer"]')).not.toBeNull();
  });

  test('« Reessayer » repare la section, sans recharger la page', async () => {
    localStorage.setItem('afroboost_jwt', jetonValide());
    let tour = 0;
    routerAxios({
      '/contacts/all': () => {
        tour += 1;
        return tour === 1
          ? Promise.reject({ response: { status: 500 } })
          : Promise.resolve(reponseContacts([
              { id: '1', name: 'A', email: 'a@x.ch', type: 'user' },
              { id: '2', name: 'B', email: 'b@x.ch', type: 'user' },
            ]));
      },
      '/contact-categories': { data: { success: true, categories: [] } },
      '/google-contacts/status': { data: { connected: false } },
    });

    await rendre();
    const bouton = conteneur.querySelector('[data-testid="bouton-reessayer"]');
    expect(bouton).not.toBeNull();

    await act(async () => {
      bouton.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    const apres = compteurs();
    expect(apres[0].etat).toBe('ok');
    expect(apres[0].texte).toBe('2');
    expect(conteneur.querySelector('[data-testid="erreur-contacts-contacts"]')).toBeNull();
  });
});

describe('Contacts — le vide REEL reste du vide', () => {
  test('une liste vraiment vide affiche bien 0', async () => {
    localStorage.setItem('afroboost_jwt', jetonValide());
    routerAxios({
      '/contacts/all': reponseContacts([]),
      '/contact-categories': { data: { success: true, categories: [] } },
      '/google-contacts/status': { data: { connected: false } },
    });

    await rendre();

    const c = compteurs();
    expect(c[0].etat).toBe('ok');
    expect(c[0].texte).toBe('0'); // ici, le zero est VRAI — il doit s'afficher
    expect(conteneur.querySelector('[data-testid="erreur-contacts-contacts"]')).toBeNull();
  });

  test('`success: false` n\'est PAS pris pour une liste vide', async () => {
    localStorage.setItem('afroboost_jwt', jetonValide());
    routerAxios({
      '/contacts/all': { data: { success: false } },
      '/contact-categories': { data: { success: true, categories: [] } },
      '/google-contacts/status': { data: { connected: false } },
    });

    await rendre();

    // Avant : `if (res.data.success)` etait faux, on ne posait rien, et les
    // compteurs restaient a 0 — indiscernable d'un compte reellement vide.
    compteurs().forEach((c) => expect(c.texte).not.toBe('0'));
  });
});

describe('Contacts — succes normal', () => {
  test('les contacts recus s\'affichent et aucune erreur n\'est montree', async () => {
    localStorage.setItem('afroboost_jwt', jetonValide());
    routerAxios({
      '/contacts/all': reponseContacts([
        { id: '1', name: 'Ana', email: 'ana@x.ch', type: 'user' },
        { id: '2', name: 'Bo', email: 'bo@x.ch', type: 'participant' },
        { id: '3', name: 'Cy', email: 'cy@x.ch', type: 'group' },
      ]),
      '/contact-categories': { data: { success: true, categories: [{ id: 'c1', name: 'VIP' }] } },
      '/google-contacts/status': { data: { connected: true, configured: true } },
    });

    await rendre();

    const c = compteurs();
    expect(c[0].etat).toBe('ok');
    expect(c[0].texte).toBe('3');
    expect(conteneur.querySelector('[data-testid="erreur-contacts-contacts"]')).toBeNull();
  });
});

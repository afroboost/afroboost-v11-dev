/**
 * ESSAI-5a-1 — la case de conditions, partagée par les trois chemins.
 *
 * Même harnais que les autres suites : react-dom/client + React.act, axios
 * remplacé par un jest.fn. Aucun réseau, aucune réservation.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import ConditionsParticipation from '../ConditionsParticipation';

jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn() } }));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const TEXTE = "Conditions de participation Afroboost.\nSection 5 : photos et vidéos.";
const AVEC = { version: 'a1b2c3d4e5f6', text: TEXTE, filmed: false, required: true };
const FILME = { ...AVEC, filmed: true };
const SANS = { version: '', text: '', filmed: false, required: false };

let conteneur = null;
let racine = null;

async function monter(donnees = AVEC, { courseId = '', accepte = false, echec = false } = {}) {
  axios.get.mockReset();
  if (echec) axios.get.mockRejectedValue(new Error('reseau'));
  else axios.get.mockResolvedValue({ data: donnees });
  const change = jest.fn();
  const requis = jest.fn();
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => {
    racine.render(
      <ConditionsParticipation courseId={courseId} accepte={accepte}
        onChange={change} onRequired={requis} />
    );
  });
  return { change, requis };
}

afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const texte = () => conteneur.textContent;

async function cliquer(id) {
  await act(async () => {
    par(id).dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
}

describe('ESSAI-5a-1 — conditions de participation', () => {
  test('U1. la case est présente, non pré-cochée, avec un lien discret', async () => {
    await monter();
    expect(par('conditions-case').checked).toBe(false);
    expect(par('conditions-lien')).not.toBeNull();
    expect(texte()).toMatch(/J'accepte les conditions de participation/);
    expect(texte()).toMatch(/Voir les conditions/);
  });

  test('U2. cocher remonte à l’appelant, jamais au serveur directement', async () => {
    const { change } = await monter();
    // React contrôle la case : il faut passer par le setter natif, sinon
    // l'événement part avec l'ancienne valeur.
    const poser = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'checked').set;
    await act(async () => {
      const el = par('conditions-case');
      poser.call(el, true);
      el.dispatchEvent(new Event('click', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(change).toHaveBeenCalledWith(true);
    expect(axios.get).toHaveBeenCalledTimes(1);   // aucune écriture, aucune 2e requête
  });

  test('U3. le détail n’occupe l’écran que si on le demande', async () => {
    await monter();
    expect(par('conditions-modal')).toBeNull();
    await cliquer('conditions-lien');
    expect(par('conditions-modal')).not.toBeNull();
    expect(texte()).toMatch(/Section 5 : photos et vidéos/);
  });

  test('U4. la modal se ferme par ✕ et par clic extérieur, sans rien perdre', async () => {
    const { change } = await monter();
    await cliquer('conditions-lien');
    await cliquer('conditions-fermer');
    expect(par('conditions-modal')).toBeNull();
    await cliquer('conditions-lien');
    await act(async () => {
      par('conditions-modal').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(par('conditions-modal')).toBeNull();
    expect(par('conditions-case')).not.toBeNull();   // la case est toujours là
    expect(change).not.toHaveBeenCalled();           // ouvrir n’a rien accepté
  });

  test('F1. cours filmé → la mention de captation est visible avant de confirmer', async () => {
    await monter(FILME, { courseId: 'c-filme' });
    expect(par('conditions-captation')).not.toBeNull();
    expect(texte()).toMatch(/susceptible d'être photographiée ou filmée/);
    expect(texte()).toMatch(/conditions de participation et d'image/);
    expect(axios.get.mock.calls[0][1].params.course_id).toBe('c-filme');
  });

  test('F2. cours non filmé → aucune mention de captation', async () => {
    await monter(AVEC, { courseId: 'c-non' });
    expect(par('conditions-captation')).toBeNull();
    expect(texte()).not.toMatch(/filmée/);
    expect(texte()).not.toMatch(/et d'image/);
  });

  test('D1. aucune condition publiée → rien ne s’affiche et rien ne bloque', async () => {
    const { requis } = await monter(SANS);
    expect(par('conditions-participation')).toBeNull();
    expect(conteneur.textContent).toBe('');
    expect(requis).toHaveBeenCalledWith(false);
  });

  test('D2. conditions publiées → l’appelant est prévenu qu’il doit bloquer', async () => {
    const { requis } = await monter(AVEC);
    expect(requis).toHaveBeenCalledWith(true);
  });

  test('D3. une lecture en échec ne bloque pas la réservation — le serveur décide', async () => {
    const { requis } = await monter(AVEC, { echec: true });
    expect(par('conditions-participation')).toBeNull();
    expect(requis).toHaveBeenCalledWith(false);
  });

  test('P1. aucune donnée personnelle n’est envoyée pour lire les conditions', async () => {
    await monter(AVEC, { courseId: 'c1' });
    const envoye = JSON.stringify(axios.get.mock.calls);
    expect(envoye).not.toMatch(/email|code|whatsapp|phone|user/i);
  });
});

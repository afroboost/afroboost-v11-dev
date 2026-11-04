// V646 — la FAQ passe par `fetch`, qui ne reçoit pas le jeton de l'intercepteur axios.
// Sans ce jeton, le serveur refuse désormais l'écriture : elle doit le joindre, et un refus
// ne doit jamais effacer le texte que le coach vient de saisir.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import FAQManager from '../FAQManager';

global.IS_REACT_ACT_ENVIRONMENT = true;
const API = 'http://banc.test/api';
let conteneur;
let racine;

function reponse(ok, corps) {
  return Promise.resolve({ ok, status: ok ? 200 : 401, json: () => Promise.resolve(corps) });
}

const ecritures = () => global.fetch.mock.calls.filter(([, o]) => o && o.method && o.method !== 'GET');
const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);

function saisir(el, valeur) {
  const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, valeur);
  el.dispatchEvent(new Event('input', { bubbles: true }));
}

async function saisirEtEnvoyer(texte) {
  await act(async () => {
    racine.render(<FAQManager API={API} coachEmail="coach@example.test" t={(c) => c} />);
  });
  await act(async () => { saisir(par('faq-question-input'), texte); });
  await act(async () => { saisir(par('faq-answer-input'), 'Réponse'); });
  await act(async () => {
    par('faq-question-input').closest('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  });
}

describe('FAQManager : écriture signée', () => {
  beforeEach(() => {
    conteneur = document.createElement('div');
    document.body.appendChild(conteneur);
    racine = createRoot(conteneur);
    localStorage.setItem('afroboost_jwt', 'jeton-de-banc');
    window.alert = jest.fn();
    global.fetch = jest.fn((url, o) => (o && o.method ? reponse(true, {}) : reponse(true, [])));
  });
  afterEach(async () => {
    await act(async () => { racine.unmount(); });
    conteneur.remove();
    localStorage.clear();
    delete global.fetch;
  });

  test('la création joint le jeton de session', async () => {
    await saisirEtEnvoyer('Horaires ?');
    expect(ecritures()).toHaveLength(1);
    const [url, options] = ecritures()[0];
    expect(url).toBe(`${API}/coach/faq`);
    expect(options.headers.Authorization).toBe('Bearer jeton-de-banc');
  });

  test('accepté : le formulaire se vide', async () => {
    await saisirEtEnvoyer('Horaires ?');
    expect(par('faq-question-input').value).toBe('');
    expect(window.alert).not.toHaveBeenCalled();
  });

  test('refusé : le texte saisi reste et le coach est prévenu', async () => {
    global.fetch = jest.fn((url, o) => (o && o.method ? reponse(false, {}) : reponse(true, [])));
    await saisirEtEnvoyer('Texte à ne pas perdre');
    expect(window.alert).toHaveBeenCalled();
    expect(par('faq-question-input').value).toBe('Texte à ne pas perdre');
  });
});

// CAL-2 — LE PANNEAU DES TÂCHES, vu du navigateur.
//
// CE QUI EST PROUVÉ ICI :
//
//   * une tâche se crée avec un titre, une échéance et une priorité, et la
//     requête part bien vers `/calendar-events` avec `event_type: task` — la
//     même route que le reste du calendrier, pas une seconde ;
//   * terminer et rouvrir passent par le MÊME champ, le statut : une route
//     « terminer » dédiée aurait fini par diverger ;
//   * les quatre piles filtrent, et « en retard » se voit d'un coup d'œil —
//     c'est la seule information soulignée par une couleur fixe, parce qu'elle
//     doit alerter quelle que soit la marque du coach ;
//   * une liste vide le dit, au lieu d'un zéro muet ;
//   * un refus du serveur est annoncé sans casser l'écran ;
//   * aucune couleur de marque codée en dur, aucun Google.
//
// `axios` est mocké : aucun appel réseau ne part de ces tests.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import axios from 'axios';
import TasksPanel from '../TasksPanel';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), patch: jest.fn(), delete: jest.fn() },
}));

let conteneur = null;
let racine = null;

async function monter(element) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(element); });
  return conteneur;
}

beforeEach(() => {
  axios.post.mockReset(); axios.patch.mockReset();
  axios.post.mockResolvedValue({ data: {} });
  axios.patch.mockResolvedValue({ data: {} });
});

afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) document.body.removeChild(conteneur);
  racine = null; conteneur = null;
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const tous = (sel) => Array.from(conteneur.querySelectorAll(sel));
const cliquer = (el) => act(async () => {
  el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
});

function saisir(element, valeur) {
  const proto = element instanceof HTMLSelectElement
    ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
  setter.call(element, valeur);
  element.dispatchEvent(new Event('change', { bubbles: true }));
  element.dispatchEvent(new Event('input', { bubbles: true }));
}

const tache = (extra = {}) => ({
  id: 't-1', title: 'Vérifier DKIM Resend', starts_at: '2026-09-05T14:00:00+00:00',
  event_type: 'task', status: 'prevu', priority: 'normale', bucket: 'a_venir',
  completed_at: null, ...extra,
});

// ---------------------------------------------------------------------------
describe('CAL-2 — créer une tâche', () => {
  test('le formulaire s’ouvre sur demande, pas avant', async () => {
    await monter(<TasksPanel taches={[]} />);
    expect(par('formulaire-tache')).toBeNull();
    await cliquer(par('nouvelle-tache'));
    expect(par('formulaire-tache')).toBeTruthy();
  });

  test('l’échéance est pré-remplie — on ne demande pas de tout saisir', async () => {
    await monter(<TasksPanel taches={[]} />);
    await cliquer(par('nouvelle-tache'));
    expect(par('tache-echeance').value).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
  });

  test('la création part sur /calendar-events avec event_type task', async () => {
    await monter(<TasksPanel API="/api-base" taches={[]} onRecharger={() => {}} />);
    await cliquer(par('nouvelle-tache'));
    saisir(par('tache-titre'), 'Appeler Festival X');
    saisir(par('tache-priorite'), 'haute');
    await cliquer(par('tache-enregistrer'));
    expect(axios.post).toHaveBeenCalledTimes(1);
    const [url, corps] = axios.post.mock.calls[0];
    expect(url).toContain('/calendar-events');
    expect(corps.event_type).toBe('task');
    expect(corps.title).toBe('Appeler Festival X');
    expect(corps.priority).toBe('haute');
    expect(corps.starts_at).toMatch(/Z$/);   // ISO, pas la valeur du champ local
  });

  test('sans titre, RIEN n’est envoyé et l’écran le dit', async () => {
    await monter(<TasksPanel taches={[]} />);
    await cliquer(par('nouvelle-tache'));
    await cliquer(par('tache-enregistrer'));
    expect(axios.post).not.toHaveBeenCalled();
    expect(par('message-tache')).toBeTruthy();
  });

  test('un refus du serveur est annoncé, sans casser l’écran', async () => {
    axios.post.mockRejectedValue(new Error('refus'));
    await monter(<TasksPanel taches={[]} />);
    await cliquer(par('nouvelle-tache'));
    saisir(par('tache-titre'), 'x');
    await cliquer(par('tache-enregistrer'));
    expect(par('message-tache').textContent).toContain('refusée');
    expect(par('panneau-taches')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
describe('CAL-2 — terminer et rouvrir', () => {
  test('terminer envoie un statut, pas une route dédiée', async () => {
    await monter(<TasksPanel taches={[tache()]} onRecharger={() => {}} />);
    await cliquer(par('basculer-tache'));
    expect(axios.patch).toHaveBeenCalledTimes(1);
    const [url, corps] = axios.patch.mock.calls[0];
    expect(url).toContain('/calendar-events/t-1');
    expect(corps).toEqual({ status: 'fait' });
  });

  test('une tâche faite se rouvre par le même chemin', async () => {
    await monter(<TasksPanel taches={[tache({ status: 'fait', bucket: 'terminees' })]}
                             onRecharger={() => {}} />);
    await cliquer(par('basculer-tache'));
    expect(axios.patch.mock.calls[0][1]).toEqual({ status: 'prevu' });
  });

  test('une tâche faite est barrée et atténuée', async () => {
    await monter(<TasksPanel taches={[tache({ status: 'fait', bucket: 'terminees' })]} />);
    const ligne = par('tache-ligne');
    expect(ligne.style.opacity).toBe('0.6');
    expect(ligne.querySelector('span').style.textDecoration).toContain('line-through');
  });

  test('le bouton dit ce qu’il fait (accessibilité)', async () => {
    await monter(<TasksPanel taches={[tache()]} />);
    expect(par('basculer-tache').getAttribute('aria-label')).toBe('Terminer la tâche');
  });
});

// ---------------------------------------------------------------------------
describe('CAL-2 — les quatre piles', () => {
  test('les cinq boutons de pile existent', async () => {
    await monter(<TasksPanel taches={[]} />);
    ['toutes', 'aujourdhui', 'en_retard', 'a_venir', 'terminees']
      .forEach((p) => expect(par(`pile-${p}`)).toBeTruthy());
  });

  test('choisir une pile remonte au parent — la liste vient du serveur', async () => {
    const choix = [];
    await monter(<TasksPanel taches={[]} onChangerPile={(p) => choix.push(p)} />);
    await cliquer(par('pile-en_retard'));
    expect(choix).toEqual(['en_retard']);
  });

  test('les compteurs du serveur sont affichés', async () => {
    await monter(<TasksPanel taches={[]}
                             compteurs={{ aujourdhui: 2, en_retard: 3, a_venir: 5, terminees: 9 }} />);
    expect(par('pile-en_retard').textContent).toContain('3');
    expect(par('pile-terminees').textContent).toContain('9');
  });

  test('le retard est signalé en tête, avec une couleur d’alerte', async () => {
    await monter(<TasksPanel taches={[]} compteurs={{ en_retard: 4 }} />);
    const badge = par('compteur-retard');
    expect(badge.textContent).toContain('4');
    expect(badge.style.background).toContain('239');   // rouge sémantique
  });

  test('sans retard, aucun badge — pas d’alarme permanente', async () => {
    await monter(<TasksPanel taches={[]} compteurs={{ en_retard: 0, a_venir: 3 }} />);
    expect(par('compteur-retard')).toBeNull();
  });

  test('une tâche en retard porte la barre d’alerte', async () => {
    await monter(<TasksPanel taches={[tache({ bucket: 'en_retard' })]} />);
    expect(par('tache-ligne').style.borderLeft).toContain('239');
  });
});

// ---------------------------------------------------------------------------
describe('CAL-2 — présentation et robustesse', () => {
  test('une liste vide le DIT', async () => {
    await monter(<TasksPanel taches={[]} />);
    expect(par('taches-vide')).toBeTruthy();
    expect(par('taches-vide').textContent).toContain('Aucune tâche');
  });

  test('la priorité haute est visible, les autres non', async () => {
    await monter(<TasksPanel taches={[tache({ priority: 'haute' })]} />);
    expect(par('priorite-haute')).toBeTruthy();
    await act(async () => { racine.render(<TasksPanel taches={[tache()]} />); });
    expect(par('priorite-haute')).toBeNull();
  });

  test('l’échéance est lisible, pas un ISO brut', async () => {
    await monter(<TasksPanel taches={[tache()]} />);
    expect(par('tache-ligne').textContent).toMatch(/\d{2}\/\d{2} \d{2}:\d{2}/);
    expect(par('tache-ligne').textContent).not.toContain('+00:00');
  });

  test('une échéance illisible n’affiche rien plutôt qu’une date fausse', async () => {
    await monter(<TasksPanel taches={[tache({ starts_at: 'n’importe quoi' })]} />);
    expect(par('tache-ligne')).toBeTruthy();
    expect(par('tache-ligne').textContent).not.toMatch(/NaN|Invalid/);
  });

  test('plusieurs tâches, une ligne chacune', async () => {
    await monter(<TasksPanel taches={[tache(), tache({ id: 't-2', title: 'Deux' })]} />);
    expect(tous('[data-testid="tache-ligne"]').length).toBe(2);
  });

  test('le panneau ne déborde jamais horizontalement (mobile)', async () => {
    await monter(<TasksPanel taches={[tache({ title: 'x'.repeat(200) })]} />);
    expect(par('panneau-taches').style.maxWidth).toBe('100%');
    expect(par('panneau-taches').style.overflow).toBe('hidden');
    const titre = par('tache-ligne').querySelector('span');
    expect(titre.style.textOverflow).toBe('ellipsis');
  });
});

// ---------------------------------------------------------------------------
describe('CAL-2 — couleurs et indépendance', () => {
  const BRUT = require('fs').readFileSync(
    require('path').join(__dirname, '..', 'TasksPanel.js'), 'utf8');
  // On inspecte le CODE : l'en-tête cite les règles, pas les valeurs.
  const SOURCE = BRUT.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');

  test('le panneau utilise les variables CSS du dépôt', () => {
    expect(SOURCE).toContain('var(--primary-color');
    expect(SOURCE).toContain('var(--primary-rgb');
  });

  test('aucune couleur de MARQUE codée en dur', () => {
    const hex = (SOURCE.match(/#[0-9a-fA-F]{6}/g) || [])
      .filter((h) => h !== '#D91CD2' && h.toLowerCase() !== '#fff');
    expect(hex).toEqual([]);
  });

  test('aucune dépendance Google', () => {
    ['google', 'Google', 'oauth', 'gapi'].forEach((m) => expect(SOURCE).not.toContain(m));
  });

  test('le panneau n’écrit que dans /calendar-events — pas de seconde collection', () => {
    const urls = SOURCE.match(/\$\{base\}\/[a-z-]+/g) || [];
    expect([...new Set(urls)]).toEqual(['${base}/calendar-events']);
  });
});

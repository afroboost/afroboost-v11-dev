/**
 * RAPPELS V2 — niveau 1 : le coach choisit quels cours envoient des rappels.
 *
 * Meme harnais que ReminderRulesCard.test.js : react-dom/client + React.act,
 * axios remplace par deux jest.fn. Aucun reseau, aucun envoi.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import CourseRemindersCard from '../CourseRemindersCard';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), put: jest.fn() }
}));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const R24H = { type: 'relative', minutes: 1440 };
const SD700 = { type: 'same_day', heure: 7, minute: 0 };

// Les vrais cours du coach : recurrents, a 18:30, et NON publies.
const MERCREDI = {
  id: 'merc', name: 'Afroboost Silent', weekday: 3, time: '18:30',
  visible: false, archived: false
};
const DIMANCHE = {
  id: 'dim', name: 'Sunday Vibes', weekday: 0, time: '18:30',
  visible: false, archived: false,
  reminders_enabled: true, reminder_rules: [R24H, SD700]
};
const ARCHIVE = {
  id: 'vieux', name: 'Ancien cours', weekday: 1, time: '19:00',
  visible: true, archived: true
};

let conteneur = null;
let racine = null;

async function monter({ cours = [MERCREDI, DIMANCHE], echecGet = null } = {}) {
  axios.get.mockReset();
  axios.put.mockReset();
  if (echecGet) axios.get.mockRejectedValue(echecGet);
  else axios.get.mockResolvedValue({ data: cours });

  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => {
    racine.render(<CourseRemindersCard coachEmail="coach@afroboost.com" />);
  });
}

afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
  racine = null;
  conteneur = null;
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const texte = () => conteneur.textContent;
const valeursCours = () => Array.from(par('cr-cours').options).map((o) => o.value);

async function choisir(id, valeur) {
  const el = par(id);
  const poser = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
  await act(async () => {
    poser.call(el, valeur);
    el.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

async function cliquer(id) {
  await act(async () => {
    par(id).dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
}

describe('la liste des cours a configurer', () => {
  test('elle vient de la portee du coach, identite en en-tete', async () => {
    await monter();
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(axios.get.mock.calls[0][0]).toBe('/api/courses?scope=mine');
    expect(axios.get.mock.calls[0][1].headers['X-User-Email']).toBe('coach@afroboost.com');
  });

  test('un cours NON PUBLIE reste selectionnable — c\'est le cas de tous mes recurrents', async () => {
    await monter();
    expect(valeursCours()).toEqual(['merc', 'dim']);
    expect(MERCREDI.visible).toBe(false);
  });

  test('et on le dit au coach, pour qu\'il ne croie pas a une erreur', async () => {
    await monter();
    expect(par('cr-non-publie')).not.toBeNull();
  });

  test('un cours ARCHIVE n\'est pas proposé', async () => {
    await monter({ cours: [MERCREDI, ARCHIVE, DIMANCHE] });
    expect(valeursCours()).toEqual(['merc', 'dim']);
    expect(texte()).not.toContain('Ancien cours');
  });

  test('le jour et l\'heure figurent dans le libelle — mercredi et dimanche 18:30', async () => {
    await monter();
    const libelles = Array.from(par('cr-cours').options).map((o) => o.textContent);
    expect(libelles[0]).toContain('Mercredi');
    expect(libelles[0]).toContain('18:30');
    expect(libelles[1]).toContain('Dimanche');
    expect(libelles[1]).toContain('18:30');
  });

  test('aucun cours du tout : on le dit, sans editeur mort', async () => {
    await monter({ cours: [] });
    expect(par('cr-aucun-cours')).not.toBeNull();
    expect(par('cr-actif')).toBeNull();
  });
});

describe('activation par cours', () => {
  test('un cours jamais configure arrive ETEINT', async () => {
    await monter();
    expect(par('cr-actif').getAttribute('aria-checked')).toBe('false');
    expect(par('cr-moment-0')).toBeNull();
  });

  test('les moments n\'apparaissent qu\'une fois les rappels allumes', async () => {
    await monter();
    await cliquer('cr-actif');
    expect(par('cr-actif').getAttribute('aria-checked')).toBe('true');
    expect(par('cr-moment-0')).not.toBeNull();
  });

  test('la proposition par defaut est bien « la veille » + « le jour meme »', async () => {
    await monter();
    await cliquer('cr-actif');
    expect(par('cr-moment-0').value).toBe('rel:1440');
    expect(par('cr-moment-1').value).toBe('same_day');
    expect(par('cr-heure-1').value).toBe('7:0');
  });

  test('un cours deja configure arrive ALLUME, avec ses propres regles', async () => {
    await monter();
    await choisir('cr-cours', 'dim');
    expect(par('cr-actif').getAttribute('aria-checked')).toBe('true');
    expect(par('cr-moment-0').value).toBe('rel:1440');
    expect(par('cr-moment-1').value).toBe('same_day');
  });

  test('changer de cours recharge SA configuration, pas celle du precedent', async () => {
    await monter();
    await choisir('cr-cours', 'dim');
    expect(par('cr-moment-0')).not.toBeNull();
    await choisir('cr-cours', 'merc');
    expect(par('cr-actif').getAttribute('aria-checked')).toBe('false');
    expect(par('cr-moment-0')).toBeNull();
  });

  test('le fuseau est rappele des que des moments sont regles', async () => {
    await monter();
    await cliquer('cr-actif');
    expect(par('cr-fuseau').textContent).toContain('Europe/Zurich');
  });
});

describe('enregistrement', () => {
  test('rien a enregistrer tant que rien n\'a change', async () => {
    await monter();
    expect(par('cr-enregistrer').disabled).toBe(true);
  });

  test('l\'activation part au serveur sur la route du COURS choisi', async () => {
    await monter();
    axios.put.mockResolvedValue({
      data: { success: true, reminders_enabled: true, rules: [R24H, SD700] }
    });
    await cliquer('cr-actif');
    await cliquer('cr-enregistrer');
    expect(axios.put.mock.calls[0][0]).toBe('/api/coach/courses/merc/reminders');
    expect(axios.put.mock.calls[0][1]).toEqual({ enabled: true, rules: [R24H, SD700] });
    expect(axios.put.mock.calls[0][2].headers['X-User-Email']).toBe('coach@afroboost.com');
  });

  test('couper les rappels envoie enabled=false', async () => {
    await monter();
    axios.put.mockResolvedValue({ data: { success: true, reminders_enabled: false, rules: [] } });
    await choisir('cr-cours', 'dim');
    await cliquer('cr-actif');
    await cliquer('cr-enregistrer');
    expect(axios.put.mock.calls[0][0]).toBe('/api/coach/courses/dim/reminders');
    expect(axios.put.mock.calls[0][1].enabled).toBe(false);
  });

  test('« Enregistré » s\'affiche et le bouton se rendort', async () => {
    await monter();
    axios.put.mockResolvedValue({
      data: { success: true, reminders_enabled: true, rules: [R24H, SD700] }
    });
    await cliquer('cr-actif');
    await cliquer('cr-enregistrer');
    expect(par('cr-confirme')).not.toBeNull();
    expect(par('cr-enregistrer').disabled).toBe(true);
  });

  test('deux rappels identiques sont refuses AVANT le serveur', async () => {
    await monter();
    await cliquer('cr-actif');
    await choisir('cr-moment-1', 'rel:1440');
    expect(par('cr-refus')).not.toBeNull();
    expect(par('cr-enregistrer').disabled).toBe(true);
    expect(axios.put).not.toHaveBeenCalled();
  });

  test('le refus du serveur est montre mot pour mot', async () => {
    await monter();
    axios.put.mockRejectedValue({ response: { status: 400, data: { detail: 'Motif du serveur.' } } });
    await cliquer('cr-actif');
    await cliquer('cr-enregistrer');
    expect(par('cr-erreur').textContent).toBe('Motif du serveur.');
    expect(par('cr-confirme')).toBeNull();
  });
});

describe('erreurs de chargement', () => {
  test('session non reconnue : on invite a se reconnecter, aucun editeur', async () => {
    await monter({ echecGet: { response: { status: 401 } } });
    expect(texte()).toContain('Reconnecte-toi pour régler tes rappels.');
    expect(par('cr-cours')).toBeNull();
    expect(par('cr-enregistrer')).toBeNull();
  });

  test('panne reseau : message generique, pas de formulaire mort', async () => {
    await monter({ echecGet: new Error('Network Error') });
    expect(texte()).toContain('Réglage des rappels indisponible pour le moment.');
    expect(par('cr-cours')).toBeNull();
  });
});

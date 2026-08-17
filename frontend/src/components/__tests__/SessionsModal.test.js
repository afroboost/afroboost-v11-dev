/**
 * Le calendrier des sessions s'ouvre PAR-DESSUS la vitrine, jamais a sa place,
 * et il consomme la MEME source d'horaires que les cartes d'offres.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import SessionsModal, {
  lireHeure, occurrencesDesCours, instantLocal, normaliserAgenda
} from '../SessionsModal';

jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn() } }));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const defilements = [];
beforeAll(() => { window.scrollTo = (x, y) => { defilements.push([x, y]); }; });

// --- occurrences telles que le serveur les rend (forme reelle) -------------
const occ = (course_id, name, datetime, extra = {}) => ({
  course_id, name, datetime, date: datetime.slice(0, 10),
  time: datetime.slice(11, 16), locationName: 'Neuchâtel',
  recurrent: true, offers: [{ id: 'pulse', name: 'PULSE x10 cours' }], ...extra
});

const AGENDA = [
  occ('merc', 'Afroboost Silent – Session Cardio', '2026-08-19T18:30:00',
      { offers: [{ id: 'pulse', name: 'PULSE x10 cours' }, { id: 'membres', name: 'Membres' }] }),
  occ('laff', 'Laff Festival', '2026-08-21T18:30:00',
      { recurrent: false, is_fixed_date: true, locationName: 'Lausanne' }),
  occ('dim', 'Afroboost Silent – Sunday Vibes', '2026-08-23T18:30:00'),
  occ('merc', 'Afroboost Silent – Session Cardio', '2026-08-26T18:30:00'),
  occ('dim', 'Afroboost Silent – Sunday Vibes', '2026-08-30T18:30:00')
];

const COURS_REPLI = [
  { id: 'evt', name: 'Atelier de repli', date: '2030-06-14', time: '14:00', visible: true, archived: false }
];

let conteneur = null;
let racine = null;
let fermetures = 0;
let reservations = [];

async function monter({ agenda = AGENDA, open = true, echec = false, cours = COURS_REPLI } = {}) {
  fermetures = 0; reservations = []; defilements.length = 0;
  axios.get.mockReset();
  if (echec) axios.get.mockRejectedValue(new Error('route absente'));
  else axios.get.mockResolvedValue({ data: { occurrences: agenda } });

  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => {
    racine.render(
      <SessionsModal open={open} onClose={() => { fermetures += 1; }}
        courses={cours} onReserve={(o) => reservations.push(o)} />
    );
  });
  await act(async () => {});
}

async function demonter() {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
}

afterEach(async () => {
  await demonter();
  document.documentElement.style.removeProperty('overflow');
  document.body.style.removeProperty('overflow');
});

const par = (id) => document.querySelector(`[data-testid="${id}"]`);
const tous = (sel) => Array.from(document.querySelectorAll(sel));
async function cliquer(el) {
  await act(async () => { el.dispatchEvent(new MouseEvent('click', { bubbles: true })); });
}

describe('lecture des donnees serveur', () => {
  test('un instant ISO naif est une heure LOCALE, pas de l\'UTC', () => {
    const d = instantLocal('2026-08-19T18:30:00');
    expect(d.getFullYear()).toBe(2026);
    expect(d.getMonth()).toBe(7);
    expect(d.getDate()).toBe(19);
    expect(d.getHours()).toBe(18);
    expect(d.getMinutes()).toBe(30);
    expect(d.getDay()).toBe(3);          // mercredi
  });

  test('une date illisible est ecartee au lieu de produire une occurrence fausse', () => {
    expect(instantLocal('n importe quoi')).toBeNull();
    expect(instantLocal(null)).toBeNull();
    expect(normaliserAgenda([{ course_id: 'x', datetime: 'casse' }])).toHaveLength(0);
  });

  test('la normalisation garde le cours, le lieu, le type et les offres', () => {
    const [a] = normaliserAgenda([AGENDA[0]]);
    expect(a.id).toBe('merc');
    expect(a.lieu).toBe('Neuchâtel');
    expect(a.ponctuel).toBe(false);
    expect(a.offres.map((o) => o.id)).toEqual(['pulse', 'membres']);
  });

  test('un evenement date est marque ponctuel', () => {
    const [a] = normaliserAgenda([AGENDA[1]]);
    expect(a.ponctuel).toBe(true);
  });

  test('les occurrences sont retriees, quoi qu\'envoie le serveur', () => {
    const melange = [AGENDA[4], AGENDA[0], AGENDA[2]];
    const n = normaliserAgenda(melange);
    expect(n.map((x) => x.quand.getDate())).toEqual([19, 23, 30]);
  });
});

describe('le cas reel : PULSE x10 et Membres, mercredi + dimanche', () => {
  test('les occurrences recurrentes sont bien affichees', async () => {
    await monter();
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(axios.get.mock.calls[0][0]).toBe('/api/sessions/agenda');
    expect(par('sessions-vide')).toBeNull();
    expect(tous('[data-testid^="sessions-jour-"]').length).toBe(5);
  });

  test('les jours marques d\'aout sont 19, 21, 23, 26 et 30', async () => {
    await monter();
    const ids = tous('[data-testid^="sessions-jour-"]')
      .map((b) => b.getAttribute('data-testid').replace('sessions-jour-', ''));
    expect(ids).toEqual(['2026-08-19', '2026-08-21', '2026-08-23', '2026-08-26', '2026-08-30']);
  });

  test('deux offres sur la meme seance ne font PAS deux lignes', async () => {
    await monter();
    expect(tous('[data-testid^="sessions-occurrence-"]').length).toBe(1);
    expect(par('sessions-occurrence-0').textContent).toContain('Session Cardio');
  });

  test('le detail affiche la bonne date, la bonne heure et le bon lieu', async () => {
    await monter();
    await cliquer(par('sessions-occurrence-0'));
    const t = par('sessions-detail').textContent;
    expect(t).toContain('mercredi 19 août 2026');
    expect(t).toContain('18:30');
    expect(t).toContain('Neuchâtel');
    expect(t).toContain('Chaque mercredi');
  });

  test('un evenement date est presente comme une date unique', async () => {
    await monter({ agenda: [AGENDA[1]] });
    await cliquer(par('sessions-occurrence-0'));
    expect(par('sessions-detail').textContent).toContain('date unique');
  });
});

describe('repli quand la route n\'est pas servie', () => {
  test('le calendrier retombe sur les cours publies plutot que de rester vide', async () => {
    await monter({ echec: true });
    expect(par('sessions-vide')).toBeNull();
    expect(par('sessions-mois')).not.toBeNull();
  });

  test('et il n\'affiche rien du tout si meme le repli est vide', async () => {
    await monter({ echec: true, cours: [] });
    expect(par('sessions-vide')).not.toBeNull();
  });
});

describe('calcul local de repli', () => {
  test('« 18:30 » et « 18h30 » sont lus pareil, le reste retombe sur 09:00', () => {
    expect(lireHeure('18:30')).toEqual({ heure: 18, minute: 30 });
    expect(lireHeure('18h30')).toEqual({ heure: 18, minute: 30 });
    expect(lireHeure('')).toEqual({ heure: 9, minute: 0 });
  });

  test('weekday 0 est DIMANCHE, pas lundi', () => {
    const o = occurrencesDesCours(
      [{ id: 'd', name: 'x', weekday: 0, time: '18:30', visible: true }], 14, new Date(2026, 7, 17));
    expect(o[0].quand.getDay()).toBe(0);
    expect(o[0].quand.getDate()).toBe(23);
  });

  test('un cours ponctuel deja passe disparait, avec 2 h de tolerance', () => {
    const c = [{ id: 'e', name: 'x', date: '2030-06-14', time: '14:00', visible: true }];
    expect(occurrencesDesCours(c, 365, new Date(2030, 5, 14, 15, 30))).toHaveLength(1);
    expect(occurrencesDesCours(c, 365, new Date(2030, 5, 14, 17, 0))).toHaveLength(0);
  });
});

describe('la fenetre s\'ouvre par-dessus la page', () => {
  test('fermee, elle ne rend rien et n\'appelle pas le serveur', async () => {
    await monter({ open: false });
    expect(par('sessions-modal')).toBeNull();
    expect(axios.get).not.toHaveBeenCalled();
  });

  test('ouverte, elle se rend par PORTAIL hors de son conteneur parent', async () => {
    await monter();
    expect(conteneur.contains(par('sessions-modal'))).toBe(false);
    expect(document.body.contains(par('sessions-modal'))).toBe(true);
  });

  test('elle s\'annonce comme une boite de dialogue', async () => {
    await monter();
    expect(par('sessions-modal-boite').getAttribute('role')).toBe('dialog');
    expect(par('sessions-modal-boite').getAttribute('aria-modal')).toBe('true');
  });
});

describe('le defilement de la page derriere', () => {
  test('il est verrouille en `important` — sans quoi App.css l\'emporterait', async () => {
    await monter();
    expect(document.body.style.getPropertyValue('overflow')).toBe('hidden');
    expect(document.body.style.getPropertyPriority('overflow')).toBe('important');
    expect(document.documentElement.style.getPropertyPriority('overflow')).toBe('important');
  });

  test('la position de lecture est rendue telle quelle a la fermeture', async () => {
    window.scrollY = 1234;
    await monter();
    await demonter();
    expect(document.body.style.getPropertyValue('overflow')).toBe('');
    expect(defilements[defilements.length - 1]).toEqual([0, 1234]);
  });
});

describe('navigation dans le calendrier', () => {
  test('cliquer un autre jour change la liste', async () => {
    await monter();
    await cliquer(par('sessions-jour-2026-08-23'));
    expect(par('sessions-occurrence-0').textContent).toContain('Sunday Vibes');
  });

  test('on revient au calendrier sans fermer la fenetre', async () => {
    await monter();
    await cliquer(par('sessions-occurrence-0'));
    await cliquer(par('sessions-retour'));
    expect(par('sessions-detail')).toBeNull();
    expect(fermetures).toBe(0);
  });

  test('les mois se parcourent dans les deux sens', async () => {
    await monter();
    const avant = par('sessions-mois').textContent;
    await cliquer(par('sessions-mois-suivant'));
    expect(par('sessions-mois').textContent).not.toBe(avant);
    await cliquer(par('sessions-mois-precedent'));
    expect(par('sessions-mois').textContent).toBe(avant);
  });
});

describe('fermeture', () => {
  test('par le bouton X', async () => { await monter(); await cliquer(par('sessions-fermer')); expect(fermetures).toBe(1); });
  test('par un clic sur le fond', async () => { await monter(); await cliquer(par('sessions-modal')); expect(fermetures).toBe(1); });
  test('mais PAS par un clic dans la fenetre', async () => { await monter(); await cliquer(par('sessions-modal-boite')); expect(fermetures).toBe(0); });
  test('par la touche Escape', async () => {
    await monter();
    await act(async () => { window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); });
    expect(fermetures).toBe(1);
  });
});

describe('reserver', () => {
  test('la fenetre se ferme PUIS l\'occurrence complete est remontee', async () => {
    jest.useFakeTimers();
    await monter();
    await cliquer(par('sessions-occurrence-0'));
    await act(async () => { par('sessions-reserver').dispatchEvent(new MouseEvent('click', { bubbles: true })); });
    expect(fermetures).toBe(1);
    expect(reservations).toHaveLength(0);
    await act(async () => { jest.advanceTimersByTime(100); });
    expect(reservations).toHaveLength(1);
    expect(reservations[0].id).toBe('merc');
    expect(reservations[0].offres.map((o) => o.id)).toEqual(['pulse', 'membres']);
    jest.useRealTimers();
  });
});

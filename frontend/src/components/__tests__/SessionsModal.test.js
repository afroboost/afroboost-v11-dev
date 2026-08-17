/**
 * Le calendrier des sessions s'ouvre PAR-DESSUS la vitrine, jamais a sa place.
 *
 * Meme harnais que le reste du depot : react-dom/client + React.act, pilotage
 * DOM manuel, aucune bibliotheque de rendu supplementaire.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import SessionsModal, { lireHeure, occurrencesDesCours } from '../SessionsModal';

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

// jsdom n'implemente pas le defilement : on l'observe au lieu de le subir.
const defilements = [];
beforeAll(() => {
  window.scrollTo = (x, y) => { defilements.push([x, y]); };
});

const MERCREDI = { id: 'merc', name: 'Afroboost Silent', weekday: 3, time: '18:30', locationName: 'Neuchâtel', visible: true, archived: false };
const DIMANCHE = { id: 'dim', name: 'Sunday Vibes', weekday: 0, time: '18:30', visible: true, archived: false };
const PONCTUEL = { id: 'evt', name: 'Atelier special', date: '2030-06-14', time: '14:00', archived: false };
const ARCHIVE = { id: 'vieux', name: 'Ancien', weekday: 1, time: '19:00', archived: true };
// Non publie sur la vitrine : le coach peut le configurer dans son dashboard,
// mais un visiteur n'a rien a en savoir.
const NON_PUBLIE = { id: 'brouillon', name: 'Nouveau cours', weekday: 3, time: '18:30', visible: false, archived: false };

let conteneur = null;
let racine = null;
let fermetures = 0;
let reservations = [];

async function monter({ cours = [MERCREDI, DIMANCHE], open = true } = {}) {
  fermetures = 0;
  reservations = [];
  defilements.length = 0;
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => {
    racine.render(
      <SessionsModal
        open={open}
        onClose={() => { fermetures += 1; }}
        courses={cours}
        onReserve={(c) => reservations.push(c)}
      />
    );
  });
}

async function demonter() {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
  racine = null;
  conteneur = null;
}

afterEach(async () => {
  await demonter();
  document.documentElement.style.removeProperty('overflow');
  document.body.style.removeProperty('overflow');
});

// Le composant se rend par portail : on interroge le document, pas le conteneur.
const par = (id) => document.querySelector(`[data-testid="${id}"]`);
const tous = (sel) => Array.from(document.querySelectorAll(sel));

async function cliquer(el) {
  await act(async () => {
    el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
}

describe('calcul des occurrences', () => {
  test('« 18:30 » et « 18h30 » sont lus pareil, le reste retombe sur 09:00', () => {
    expect(lireHeure('18:30')).toEqual({ heure: 18, minute: 30 });
    expect(lireHeure('18h30')).toEqual({ heure: 18, minute: 30 });
    expect(lireHeure('7')).toEqual({ heure: 7, minute: 0 });
    expect(lireHeure('')).toEqual({ heure: 9, minute: 0 });
    expect(lireHeure('n importe quoi')).toEqual({ heure: 9, minute: 0 });
    expect(lireHeure('99:99')).toEqual({ heure: 9, minute: 0 });
  });

  test('un cours recurrent revient chaque semaine, le bon jour', () => {
    const base = new Date(2026, 7, 17, 10, 0);   // lundi 17 aout 2026
    const occ = occurrencesDesCours([MERCREDI], 21, base);
    expect(occ.length).toBeGreaterThanOrEqual(3);
    occ.forEach((o) => {
      expect(o.quand.getDay()).toBe(3);          // convention JS : mercredi = 3
      expect(o.quand.getHours()).toBe(18);
      expect(o.quand.getMinutes()).toBe(30);
      expect(o.ponctuel).toBe(false);
    });
    expect(occ[0].quand.getDate()).toBe(19);     // le premier mercredi qui suit
  });

  test('weekday 0 est bien DIMANCHE, pas lundi', () => {
    const base = new Date(2026, 7, 17, 10, 0);
    const occ = occurrencesDesCours([DIMANCHE], 14, base);
    expect(occ[0].quand.getDay()).toBe(0);
    expect(occ[0].quand.getDate()).toBe(23);
  });

  test('un cours ponctuel n\'a qu\'une seule occurrence', () => {
    const base = new Date(2030, 5, 1, 10, 0);
    const occ = occurrencesDesCours([PONCTUEL], 365, base);
    expect(occ).toHaveLength(1);
    expect(occ[0].ponctuel).toBe(true);
    expect(occ[0].quand.getDate()).toBe(14);
  });

  test('un cours ponctuel deja passe disparait, avec 2 h de tolerance', () => {
    const juste_apres = new Date(2030, 5, 14, 15, 30);   // 1 h 30 apres le debut
    expect(occurrencesDesCours([PONCTUEL], 365, juste_apres)).toHaveLength(1);
    const bien_apres = new Date(2030, 5, 14, 17, 0);     // 3 h apres
    expect(occurrencesDesCours([PONCTUEL], 365, bien_apres)).toHaveLength(0);
  });

  test('un cours archive n\'apparait jamais', () => {
    expect(occurrencesDesCours([ARCHIVE], 30, new Date(2026, 7, 17))).toHaveLength(0);
  });

  test('un cours NON PUBLIE reste invisible au visiteur', () => {
    // Le calendrier EST la vitrine : `visible: false` veut dire « pas publie ».
    // C'est l'inverse exact de la carte coach, ou le meme cours doit rester
    // configurable — deux contextes, deux regles, et c'est voulu.
    expect(occurrencesDesCours([NON_PUBLIE], 14, new Date(2026, 7, 17))).toHaveLength(0);
    expect(occurrencesDesCours([MERCREDI], 14, new Date(2026, 7, 17)).length).toBeGreaterThan(0);
  });

  test('les occurrences sont rendues dans l\'ordre chronologique', () => {
    const occ = occurrencesDesCours([DIMANCHE, MERCREDI], 21, new Date(2026, 7, 17));
    for (let i = 1; i < occ.length; i += 1) {
      expect(occ[i].quand.getTime()).toBeGreaterThanOrEqual(occ[i - 1].quand.getTime());
    }
  });
});

describe('la fenetre s\'ouvre par-dessus la page', () => {
  test('fermee, elle ne rend rien du tout', async () => {
    await monter({ open: false });
    expect(par('sessions-modal')).toBeNull();
  });

  test('ouverte, elle se rend par PORTAIL hors de son conteneur parent', async () => {
    await monter();
    const modal = par('sessions-modal');
    expect(modal).not.toBeNull();
    expect(conteneur.contains(modal)).toBe(false);
    expect(document.body.contains(modal)).toBe(true);
  });

  test('le fond est assombri, et la page reste visible derriere', async () => {
    await monter();
    const modal = par('sessions-modal');
    expect(modal.style.background).toContain('rgba(0, 0, 0, 0.85)');
    expect(modal.style.position).toBe('fixed');
  });

  test('elle s\'annonce comme une boite de dialogue', async () => {
    await monter();
    const boite = par('sessions-modal-boite');
    expect(boite.getAttribute('role')).toBe('dialog');
    expect(boite.getAttribute('aria-modal')).toBe('true');
    expect(boite.getAttribute('aria-label')).toBeTruthy();
  });
});

describe('le defilement de la page derriere', () => {
  test('il est verrouille en `important` — sans quoi App.css l\'emporterait', async () => {
    await monter();
    expect(document.body.style.getPropertyPriority('overflow')).toBe('important');
    expect(document.body.style.getPropertyValue('overflow')).toBe('hidden');
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

describe('le calendrier et le detail', () => {
  test('les jours porteurs de sessions sont cliquables, les autres non', async () => {
    await monter();
    const jours = tous('[data-testid^="sessions-jour-"]');
    expect(jours.length).toBeGreaterThan(0);
    jours.forEach((j) => expect(j.disabled).toBe(false));
  });

  test('un jour est preselectionne et ses sessions sont listees', async () => {
    await monter();
    expect(par('sessions-occurrence-0')).not.toBeNull();
  });

  test('cliquer une occurrence ouvre son detail, avec le bouton Reserver', async () => {
    await monter();
    await cliquer(par('sessions-occurrence-0'));
    expect(par('sessions-detail')).not.toBeNull();
    expect(par('sessions-reserver')).not.toBeNull();
    expect(par('sessions-modal')).not.toBeNull();       // toujours dans la fenetre
  });

  test('on revient au calendrier sans fermer la fenetre', async () => {
    await monter();
    await cliquer(par('sessions-occurrence-0'));
    await cliquer(par('sessions-retour'));
    expect(par('sessions-detail')).toBeNull();
    expect(par('sessions-modal')).not.toBeNull();
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

  test('aucune session : on le dit, sans calendrier vide et trompeur', async () => {
    await monter({ cours: [ARCHIVE, NON_PUBLIE] });
    expect(par('sessions-vide')).not.toBeNull();
    expect(par('sessions-mois')).toBeNull();
  });
});

describe('fermeture', () => {
  test('par le bouton X', async () => {
    await monter();
    await cliquer(par('sessions-fermer'));
    expect(fermetures).toBe(1);
  });

  test('par un clic sur le fond', async () => {
    await monter();
    await cliquer(par('sessions-modal'));
    expect(fermetures).toBe(1);
  });

  test('mais PAS par un clic dans la fenetre elle-meme', async () => {
    await monter();
    await cliquer(par('sessions-modal-boite'));
    expect(fermetures).toBe(0);
  });

  test('par la touche Escape', async () => {
    await monter();
    await act(async () => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });
    expect(fermetures).toBe(1);
  });

  test('Escape ne fait rien quand la fenetre est fermee', async () => {
    await monter({ open: false });
    await act(async () => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });
    expect(fermetures).toBe(0);
  });
});

describe('reserver', () => {
  test('le bouton ferme la fenetre PUIS remonte le cours choisi', async () => {
    jest.useFakeTimers();
    await monter();
    await cliquer(par('sessions-occurrence-0'));
    await act(async () => {
      par('sessions-reserver').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(fermetures).toBe(1);
    expect(reservations).toHaveLength(0);     // rien avant que la fenetre soit partie
    await act(async () => { jest.advanceTimersByTime(100); });
    expect(reservations).toHaveLength(1);
    expect(reservations[0].id).toBeTruthy();
    jest.useRealTimers();
  });
});

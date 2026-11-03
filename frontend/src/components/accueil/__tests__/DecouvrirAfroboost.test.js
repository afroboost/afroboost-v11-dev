/**
 * V645.4k — « DÉCOUVRIR AFROBOOST » (panneau gauche du viewer, PC).
 *
 * Ce que ces tests verrouillent :
 *  - la prochaine séance vient de GET /api/sessions/agenda, la source de
 *    vérité du calendrier, et JAMAIS d'un calcul local (le dépôt a déjà payé
 *    cette erreur : des réservations datées de l'instant du clic) ;
 *  - « une autre séance » ne répète pas le même créneau ;
 *  - sans séance, on propose le programme plutôt qu'une date inventée ;
 *  - l'essai gratuit est reconnu par son PRIX (<= 0), seul critère réel —
 *    il n'existe aucun champ `is_trial` ;
 *  - chaque bouton délègue au parcours existant, aucun tunnel nouveau.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import DecouvrirAfroboost, { libelleSeance, offreEssai, offreVedette } from '../DecouvrirAfroboost';

jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn() } }));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

let conteneur, racine;
const appels = { seance: [], offre: [], toutes: 0, programme: 0 };

const OFFRES = [
  { id: 'essai', name: "Cours d'essai GRATUIT", price: 0, visible: true },
  { id: 'saison', name: 'Saison hiver — 8 mois', price: 549, billing_mode: 'unique', duree_mois: 8, pack_sessions: 64, visible: true },
  { id: 'mensuel', name: 'Mensuel Liberté', price: 89, billing_mode: 'mensuel_auto', visible: true },
];

// Deux cours au MÊME créneau, puis un créneau réellement différent.
const AGENDA = [
  { course_id: 'c1', name: 'Session Cardio', datetime: '2026-11-04T18:45:00', locationName: 'Valangines 97', offers: [{ id: 'essai', name: 'Essai' }], recurrent: true },
  { course_id: 'c2', name: 'Autre cours même heure', datetime: '2026-11-04T18:45:00', locationName: 'Valangines 97', offers: [], recurrent: true },
  { course_id: 'c3', name: 'Sunday Vibes', datetime: '2026-11-08T18:30:00', locationName: 'Valangines 97', offers: [], recurrent: true },
];

async function monter(occurrences) {
  axios.get.mockResolvedValue({ data: { occurrences } });
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => {
    racine.render(
      <DecouvrirAfroboost
        API="/api"
        offres={OFFRES}
        onSeance={(o) => appels.seance.push(o)}
        onOffre={(o) => appels.offre.push(o)}
        onToutesLesOffres={() => { appels.toutes += 1; }}
        onProgramme={() => { appels.programme += 1; }}
      />
    );
  });
  await act(async () => { await Promise.resolve(); });
}

beforeEach(() => {
  appels.seance = []; appels.offre = []; appels.toutes = 0; appels.programme = 0;
  jest.clearAllMocks();
});
afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const cliquer = async (id) => { await act(async () => { par(id).click(); }); };

test("la prochaine séance vient de l'agenda serveur, pas d'un calcul local", async () => {
  await monter(AGENDA);
  expect(axios.get).toHaveBeenCalledWith('/api/sessions/agenda', { params: { days: 60 } });
  const carte = par('decouvrir-prochain-cours');
  expect(carte.textContent).toContain('Session Cardio');
  expect(carte.textContent).toContain('Valangines 97');
  expect(par('decouvrir-quand').textContent).toMatch(/4 novembre/);
});

test("« une autre séance » saute les cours du MÊME créneau", async () => {
  await monter(AGENDA);
  const autre = par('decouvrir-autre-seance');
  // Le 2e cours est au même horaire : on doit proposer le 8 novembre.
  expect(autre.textContent).toMatch(/8 novembre/);
  expect(autre.textContent).not.toMatch(/4 novembre/);
});

test('réserver délègue l’occurrence COMPLÈTE au parcours existant', async () => {
  await monter(AGENDA);
  await cliquer('decouvrir-reserver');
  expect(appels.seance).toHaveLength(1);
  // L'identité de séance (cours + horaire) est transmise telle quelle.
  expect(appels.seance[0].id).toBe('c1');
  expect(appels.seance[0].quand instanceof Date).toBe(true);
  expect(appels.seance[0].offres[0].id).toBe('essai');
});

test('aucune séance : on propose le programme, jamais une date inventée', async () => {
  await monter([]);
  expect(par('decouvrir-autre-seance')).toBeNull();
  expect(par('decouvrir-reserver')).toBeNull();
  await cliquer('decouvrir-programme');
  expect(appels.programme).toBe(1);
});

test("agenda en échec : on n'invente rien, on bascule sur le programme", async () => {
  axios.get.mockRejectedValue(new Error('réseau'));
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => {
    racine.render(<DecouvrirAfroboost API="/api" offres={OFFRES} onProgramme={() => { appels.programme += 1; }} />);
  });
  await act(async () => { await Promise.resolve(); });
  expect(par('decouvrir-programme')).not.toBeNull();
  expect(par('decouvrir-quand')).toBeNull();
});

test('les offres affichées sont les vraies, essai reconnu par son prix', async () => {
  await monter(AGENDA);
  expect(par('decouvrir-essai').textContent).toContain("Cours d'essai GRATUIT");
  expect(par('decouvrir-offre-vedette').textContent).toContain('549');
  await cliquer('decouvrir-essai');
  expect(appels.offre[0].id).toBe('essai');
  await cliquer('decouvrir-toutes-offres');
  expect(appels.toutes).toBe(1);
});

test('fonctions pures : libellé Zurich, essai par prix, vedette par aimant', () => {
  expect(libelleSeance(new Date('2026-11-04T18:45:00'))).toMatch(/mercredi|Mercredi/i);
  expect(libelleSeance(null)).toBe('');
  expect(offreEssai(OFFRES).id).toBe('essai');
  expect(offreEssai([])).toBeNull();
  // Aucun champ `featured` n'existe : la vedette sort du regroupement en aimants.
  expect(offreVedette(OFFRES)).not.toBeNull();
  expect(offreVedette([])).toBeNull();
});

// V594 — le parcours simplifié d'un visiteur Partenaire, vu du navigateur.
// Composants EXISTANTS assemblés (Etapes, VignetteOffre, SessionsModal, ResumeSeance) ;
// la séance suit INV-2 (course + occurrence) et rien n'est réservé ici.
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import ParcoursPartenaire, {
  lireParcoursPartenaire, seancesCompatibles, isoMinute, ETAPES_PARCOURS_PARTENAIRE,
} from '../ParcoursPartenaire';

jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn() } }));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;
let conteneur = null;
let racine = null;
async function monter(el) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(el); });
  return conteneur;
}
afterEach(() => {
  if (racine) act(() => { racine.unmount(); });
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
  jest.resetAllMocks();
});

const OFFRE = { id: 'o-essai', name: "Cours d'essai gratuit", price: 0, linked_course_ids: ['c1'] };
// Un vendredi 18:30 dans le futur (jour réel calculé, pas écrit en dur).
const vendredi = (() => { const d = new Date(); d.setDate(d.getDate() + ((5 - d.getDay() + 7) % 7 || 7)); d.setHours(18, 30, 0, 0); return d; })();
const COURS = [
  { id: 'c1', name: 'Cardio', weekday: 5, time: '18:30', visible: true, locationName: 'Salle Test' },
  { id: 'c2', name: 'Hors offre', weekday: 5, time: '18:30', visible: true },
];
const ageIso = (d) => isoMinute(d) + ':00';
const AGENDA = [
  { course_id: 'c1', name: 'Cardio', locationName: 'Salle Test', datetime: ageIso(vendredi), offers: [] },
  { course_id: 'c2', name: 'Hors offre', datetime: ageIso(vendredi), offers: [] },
];

test('le parcours ne s’ouvre QUE pour un lien d’essai Partenaire', () => {
  expect(lireParcoursPartenaire('?offre=o-essai&reserver=1&utm_source=partenaire&utm_content=akoko'))
    .toEqual({ offre: 'o-essai' });
  expect(lireParcoursPartenaire('?offre=o-essai&reserver=1&utm_source=instagram')).toBeNull();
  expect(lireParcoursPartenaire('?offre=o-essai&utm_source=partenaire')).toBeNull();
  expect(lireParcoursPartenaire('?link=b83914b4-c5a&utm_source=partenaire')).toBeNull();
  expect(lireParcoursPartenaire('')).toBeNull();
});

test('trois étapes exactement : Séance, Informations, Confirmation', () => {
  expect(ETAPES_PARCOURS_PARTENAIRE).toEqual(['Séance', 'Informations', 'Confirmation']);
});

test('seules les séances acceptées par l’espace (règle INV-2) sont proposées', () => {
  const agenda = AGENDA.map((o) => ({ id: o.course_id, nom: o.name, lieu: '', quand: new Date(vendredi), ponctuel: false, offres: [] }));
  const s = seancesCompatibles(agenda, OFFRE, COURS);
  expect(s.map((o) => o.id)).toEqual(['c1']);            // c2 n'est pas lié à l'offre
  expect(s[0].iso).toBe(isoMinute(vendredi));
  expect(seancesCompatibles(agenda, null, COURS)).toEqual([]);
});

test('étape 1 : Continuer bloqué tant qu’aucune séance n’est choisie ; le calendrier existant la donne', async () => {
  axios.get.mockResolvedValue({ data: { occurrences: AGENDA } });
  const onSeance = jest.fn();
  const onEtape = jest.fn();
  const c = await monter(<ParcoursPartenaire offre={OFFRE} courses={COURS} analyserMedia={() => ({})}
    etape={1} onEtape={onEtape} seance={null} onSeance={onSeance} onSlotFormulaire={() => {}} onQuitter={() => {}} />);
  expect(axios.get).toHaveBeenCalledWith('/api/sessions/agenda');
  expect(c.querySelector('[data-testid="pp-etapes"]').textContent).toContain('Séance');
  expect(c.querySelector('[data-testid="pp-offre"]').textContent).toContain("Cours d'essai gratuit");
  expect(c.querySelector('[data-testid="pp-continuer"]').disabled).toBe(true);
  await act(async () => { c.querySelector('[data-testid="pp-seance-choisir"]').click(); });
  // Le calendrier EXISTANT (SessionsModal) est ouvert, rendu en portail dans le document.
  expect(document.querySelector('[data-testid="sessions-modal"]')).not.toBeNull();
  const jour = document.querySelector(`[data-testid="sessions-jour-${isoMinute(vendredi).slice(0, 10)}"]`);
  await act(async () => { jour.click(); });
  await act(async () => { document.querySelector('[data-testid="sessions-occurrence-0"]').click(); });
  await act(async () => { document.querySelector('[data-testid="sessions-reserver"]').click(); });
  // SessionsModal se ferme puis transmet la séance 60 ms plus tard (comportement existant).
  await act(async () => { await new Promise((r) => setTimeout(r, 120)); });
  expect(onSeance).toHaveBeenCalledWith({ offre: 'o-essai', course: 'c1', occurrence: isoMinute(vendredi) });
});

test('séance choisie : résumé existant + Continuer -> étape 2 ; l’étape 2 offre l’emplacement du formulaire', async () => {
  axios.get.mockResolvedValue({ data: { occurrences: AGENDA } });
  const onEtape = jest.fn();
  let slot = null;
  const seance = { offre: 'o-essai', course: 'c1', occurrence: isoMinute(vendredi) };
  const c = await monter(<ParcoursPartenaire offre={OFFRE} courses={COURS} analyserMedia={() => ({})}
    etape={1} onEtape={onEtape} seance={seance} onSeance={() => {}} onSlotFormulaire={(el) => { slot = el; }} onQuitter={() => {}} />);
  expect(c.querySelector('[data-testid="pp-seance-resume"]').textContent).toContain('Cardio');
  await act(async () => { c.querySelector('[data-testid="pp-continuer"]').click(); });
  expect(onEtape).toHaveBeenCalledWith(2);
  expect(slot).toBe(c.querySelector('[data-testid="pp-etape-informations"]'));
  expect(slot.style.display).toBe('none');             // caché à l'étape 1
});

test('aucune séance publiée : on peut continuer, la séance se choisira dans l’espace', async () => {
  axios.get.mockResolvedValue({ data: { occurrences: [] } });
  const c = await monter(<ParcoursPartenaire offre={OFFRE} courses={COURS} analyserMedia={() => ({})}
    etape={1} onEtape={() => {}} seance={null} onSeance={() => {}} onSlotFormulaire={() => {}} onQuitter={() => {}} />);
  expect(c.querySelector('[data-testid="pp-aucune-seance"]')).not.toBeNull();
  expect(c.querySelector('[data-testid="pp-continuer"]').disabled).toBe(false);
});

test('aucun composant recopié : le parcours importe les pièces existantes', () => {
  const src = require('fs').readFileSync(require('path').join(__dirname, '..', 'ParcoursPartenaire.js'), 'utf8');
  ['SessionsModal', 'VignetteOffre', 'Etapes', 'ResumeSeance', 'verdictSeanceInvitation']
    .forEach((n) => expect(src).toMatch(new RegExp(`import[^;]*\\b${n}\\b`)));
  expect(src).not.toMatch(/<form|<input|<select|<textarea/);   // le formulaire n'est PAS refait
  // Couleurs : uniquement des variables du thème ; un hex n'existe qu'en valeur de secours d'un var().
  const hexHorsVar = src.replace(/var\([^)]*\)/g, '').match(/#[0-9a-fA-F]{6}\b/g);
  expect(hexHorsVar).toBeNull();
});

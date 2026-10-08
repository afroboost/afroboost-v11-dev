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

test('le stepper existant : Séance, Coordonnées, Validation, Confirmation', () => {
  expect(ETAPES_PARCOURS_PARTENAIRE).toEqual(['Séance', 'Coordonnées', 'Validation', 'Confirmation']);
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
  // La VRAIE ligne de « Toutes les offres » (même testid que dans le panneau existant).
  expect(c.querySelector('[data-testid="pp-offre"] [data-testid="ligne-offre-o-essai"]')).not.toBeNull();
  expect(c.querySelector('[data-testid="pp-offre"]').textContent).toContain("Cours d'essai gratuit");
  expect(c.querySelector('[data-testid="pp-sans-seance"]').textContent).toBe('Aucune séance choisie');
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

test('« Voir l’offre » ouvre LA fiche existante « Détail de l’offre »', async () => {
  axios.get.mockResolvedValue({ data: { occurrences: [] } });
  const c = await monter(<ParcoursPartenaire offre={OFFRE} offres={[OFFRE]} courses={COURS} analyserMedia={() => ({})}
    etape={1} onEtape={() => {}} seance={null} onSeance={() => {}} onSlotFormulaire={() => {}} onQuitter={() => {}} />);
  expect(document.querySelector('[data-testid="fiche-offre"]')).toBeNull();
  await act(async () => { c.querySelector('[data-testid="pp-voir-offre"]').click(); });
  expect(document.querySelector('[data-testid="fiche-offre"]')).not.toBeNull();
  expect(document.querySelector('[data-testid="fiche-nom"]').textContent).toContain("Cours d'essai gratuit");
});

test('étape Coordonnées : on ne passe à « Validation » que si nom, e-mail et WhatsApp sont valides', async () => {
  axios.get.mockResolvedValue({ data: { occurrences: [] } });
  const onEtape = jest.fn();
  let slot = null;
  const c = await monter(<ParcoursPartenaire offre={OFFRE} courses={COURS} analyserMedia={() => ({})}
    etape={2} onEtape={onEtape} seance={null} onSeance={() => {}} onSlotFormulaire={(el) => { slot = el; }} onQuitter={() => {}} />);
  // App.js y rend les VRAIS champs ; on les simule ici avec leurs attributs d'origine.
  slot.innerHTML = '<input required data-testid="user-name-input"><input type="email" required data-testid="user-email-input">'
    + '<input type="tel" required data-testid="user-whatsapp-input">';
  slot.querySelectorAll('input').forEach((i) => { i.reportValidity = () => false; });
  await act(async () => { c.querySelector('[data-testid="pp-continuer-coordonnees"]').click(); });
  expect(onEtape).not.toHaveBeenCalledWith(3);
  slot.querySelector('[data-testid="user-name-input"]').value = 'Cliente Test';
  slot.querySelector('[data-testid="user-email-input"]').value = 'cliente@exemple.test';
  slot.querySelector('[data-testid="user-whatsapp-input"]').value = '+41 79 000 00 00';
  await act(async () => { c.querySelector('[data-testid="pp-continuer-coordonnees"]').click(); });
  expect(onEtape).toHaveBeenCalledWith(3);
});

test('App.js : le formulaire est découpé SANS copie, et rien ne change hors parcours Partenaire', () => {
  const app = require('fs').readFileSync(require('path').join(__dirname, '..', '..', 'App.js'), 'utf8');
  expect(app).toContain("const ppZone = (zone) => !ppActif || (zone === 'coord' ? ppEtape === 2 : ppEtape === 3);");
  ['data-testid="user-name-input"', 'data-testid="user-birthday-input"', 'data-testid="discount-code-input"',
   'data-testid="total-price"', 'data-testid="submit-reservation-btn"', '<ConditionsParticipation']
    .forEach((m) => {
      const form = app.slice(app.indexOf('{selectedOffer && ppPortail('), app.indexOf('</form>', app.indexOf('{selectedOffer && ppPortail(')));
      expect(form.split(m).length - 1).toBe(1);                   // chaque champ existe UNE fois dans le formulaire
    });
  expect(app).toContain("{ppZone('coord') && (<>");
  expect(app).toContain("{ppZone('final') && (<>");
  expect(app.match(/\{!ppActif && \(<>/g)).toHaveLength(2);    // code promo + récapitulatif de prix
});

test('aucune séance publiée : on peut continuer, la séance se choisira dans l’espace', async () => {
  axios.get.mockResolvedValue({ data: { occurrences: [] } });
  const c = await monter(<ParcoursPartenaire offre={OFFRE} courses={COURS} analyserMedia={() => ({})}
    etape={1} onEtape={() => {}} seance={null} onSeance={() => {}} onSlotFormulaire={() => {}} onQuitter={() => {}} />);
  expect(c.querySelector('[data-testid="pp-sans-seance"]').textContent).toContain('tu la choisiras dans ton espace');
  expect(c.querySelector('[data-testid="pp-continuer"]').disabled).toBe(false);
});

test('aucun composant recopié : le parcours importe les pièces existantes', () => {
  const src = require('fs').readFileSync(require('path').join(__dirname, '..', 'ParcoursPartenaire.js'), 'utf8');
  ['SessionsModal', 'LigneOffre', 'FicheOffre', 'Etapes', 'ResumeSeance', 'verdictSeanceInvitation']
    .forEach((n) => expect(src).toMatch(new RegExp(`import[^;]*\\b${n}\\b`)));
  expect(src).not.toMatch(/<form|<input|<select|<textarea/);   // le formulaire n'est PAS refait
  // Couleurs : uniquement des variables du thème ; un hex n'existe qu'en valeur de secours d'un var().
  const hexHorsVar = src.replace(/var\([^)]*\)/g, '').match(/#[0-9a-fA-F]{6}\b/g);
  expect(hexHorsVar).toBeNull();
});

test('espace client : confirmation focalisée SEULEMENT après le parcours Partenaire, rien de supprimé', () => {
  const src = require('fs').readFileSync(require('path').join(__dirname, '..', 'SubscriberSpace.js'), 'utf8');
  // activée uniquement par le parcours + une séance confirmée, et quittable
  expect(src).toContain('const v594Focus = v594Parcours && !v594Quitte && !!seanceConfirmee;');
  expect(src).toContain('get("parcours") === "partenaire"');
  // masquage CSS (aucun bloc démonté) ; seuls stepper, carte verte, bouton QR existant, sortie restent
  expect(src).toContain('[data-v594-focus] > :not([data-v594-garde]) { display: none !important; }');
  expect(src.split('data-v594-garde=""').length - 1).toBe(4);
  expect(src).toMatch(/data-testid="p2ux-confirmation"\s*\n\s*data-v594-garde=""/);
  expect(src).toContain('onClick={() => setQrFullscreen(true)}');      // le QR EXISTANT
  expect(src).toContain('data-testid="v594-acceder-espace"');
  expect(src).toContain('setV594Quitte(true)');
});

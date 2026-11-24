/**
 * V673 — message exceptionnel joint aux rappels avant cours.
 *
 * Monte la VRAIE carte « Rappels avant cours » (meme harnais que
 * CourseRemindersCard.test.js) : axios est remplace par des jest.fn.
 * Aucun reseau, aucun envoi.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import CourseRemindersCard from '../CourseRemindersCard';
import { prochaineSeance, dateLisible, periodeLisible, aujourdhuiZurich, seancesDansPeriode } from '../CourseReminderMessage';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), put: jest.fn(), delete: jest.fn() }
}));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const VENDUES = [{ id: 'pulse', name: 'PULSE x10 cours', publique: true }];
const MERCREDI = {
  id: 'merc', name: 'Session Cardio', weekday: 3, time: '18:30', visible: true,
  offres: VENDUES, reminders_enabled: true,
  reminder_rules: [{ type: 'relative', minutes: 1440 }]
};
const DIMANCHE = {
  id: 'dim', name: 'Sunday Vibes', weekday: 0, time: '18:30', visible: true,
  offres: VENDUES
};

let conteneur = null;
let racine = null;
const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const clic = async (el) => act(async () => { el.dispatchEvent(new MouseEvent('click', { bubbles: true })); });

async function saisir(el, valeur) {
  const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
  await act(async () => {
    setter.call(el, valeur);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

async function monter(cours = [MERCREDI, DIMANCHE]) {
  axios.get.mockReset(); axios.put.mockReset(); axios.delete.mockReset();
  axios.get.mockResolvedValue({ data: cours });
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(<CourseRemindersCard coachEmail="coach@exemple.com" />); });
  await clic(par('cr-bascule'));
}

afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
});

const LENDEMAIN = (() => {
  const d = new Date(`${aujourdhuiZurich()}T00:00:00Z`);
  return new Date(d.getTime() + 86400000).toISOString().slice(0, 10);
})();
// V673d : les dates de test sont de VRAIES séances (le composant refuse un autre jour).
const DEMAIN = prochaineSeance({ weekday: 3 }, LENDEMAIN);        // un mercredi
const DIM_D = prochaineSeance({ weekday: 0 }, LENDEMAIN);         // un dimanche

describe('V673 — fonctions de date', () => {
  test('prochaine séance : même jour ou jours suivants, convention JS (dim = 0)', () => {
    // 24/11/2026 est un mardi
    expect(prochaineSeance({ weekday: 3 }, '2026-11-24')).toBe('2026-11-25');
    expect(prochaineSeance({ weekday: 2 }, '2026-11-24')).toBe('2026-11-24');
    expect(prochaineSeance({ weekday: 0 }, '2026-11-24')).toBe('2026-11-29');
    expect(prochaineSeance({ date: '2026-12-05' }, '2026-11-24')).toBe('2026-12-05');
  });
  test('libellés lisibles', () => {
    expect(dateLisible('2026-11-25')).toBe('mercredi 25 novembre');
    expect(periodeLisible({ du: '2026-11-25', au: '2026-11-25' })).toBe('mercredi 25 novembre');
    expect(periodeLisible({ du: '2026-11-25', au: '2026-11-29' }))
      .toBe('du mercredi 25 novembre au dimanche 29 novembre');
  });
});

describe('V673 — message exceptionnel dans la carte des rappels', () => {
  test('rien n’apparaît tant qu’aucun cours n’est coché (carte inchangée)', async () => {
    await monter();
    // la carte coche d'elle-même les cours DÉJÀ actifs : on décoche
    const coche = par('cr-cours-merc').querySelector('input');
    if (coche.checked) await act(async () => { coche.click(); });
    expect(par('crm-zone')).toBeNull();
  });

  test('ajout : texte, date, aperçu, enregistrement sur SA route seulement', async () => {
    await monter();
    await clic(par('crm-ajouter'));
    expect(par('crm-editeur')).not.toBeNull();
    expect(par('crm-enregistrer').disabled).toBe(true);           // texte vide
    await saisir(par('crm-texte'), 'Coach Bassi absent, Marie assure le cours.');
    await saisir(par('crm-du'), DEMAIN);
    await clic(par('crm-apercu-bascule'));
    expect(par('crm-apercu-texte').textContent).toContain('Marie assure le cours');
    expect(par('crm-apercu').textContent).toContain('Session Cardio');
    expect(par('crm-apercu-push').textContent).toContain('Marie');

    axios.put.mockResolvedValue({ data: { message_exceptionnel: {
      texte: 'Coach Bassi absent, Marie assure le cours.', du: DEMAIN, au: DEMAIN } } });
    await clic(par('crm-enregistrer'));
    expect(axios.put).toHaveBeenCalledTimes(1);
    const [url, corps] = axios.put.mock.calls[0];
    expect(url).toMatch(/\/coach\/courses\/merc\/reminder-message$/);
    expect(corps).toEqual({ texte: 'Coach Bassi absent, Marie assure le cours.', du: DEMAIN, au: DEMAIN });
    // la route des réglages n'a PAS été appelée
    expect(axios.put.mock.calls.some(([u]) => /\/reminders$/.test(u))).toBe(false);
    expect(par('crm-info').textContent).toContain('Message enregistré');
    expect(par('crm-existant-merc')).not.toBeNull();
    expect(par('cr-message-merc')).not.toBeNull();
  });

  test('multi-cours : un appel par cours, CHAQUE cours reçoit SA propre date (V673d)', async () => {
    await monter();
    await act(async () => { par('cr-cours-dim').querySelector('input').click(); });
    await clic(par('crm-ajouter'));
    expect(par('crm-muets').textContent).toContain('Sunday Vibes');
    const _auj = aujourdhuiZurich();
    const _merc = prochaineSeance(MERCREDI, _auj);
    const _dim = prochaineSeance(DIMANCHE, _auj);
    expect(par('crm-du')).toBeNull();                         // plus de date commune
    expect(par('crm-du-merc').value).toBe(_merc);
    expect(par('crm-du-dim').value).toBe(_dim);
    expect(par('crm-lisible-merc').textContent).toContain('mercredi');
    expect(par('crm-lisible-dim').textContent).toContain('dimanche');
    await saisir(par('crm-texte'), 'Remplacement');
    axios.put.mockImplementation((u, c) => Promise.resolve({ data: { message_exceptionnel: c } }));
    expect(par('crm-enregistrer').textContent).toContain('2 cours');
    await clic(par('crm-enregistrer'));
    const appels = axios.put.mock.calls.filter(([u]) => /reminder-message$/.test(u));
    expect(appels).toHaveLength(2);
    const corpsDe = (id) => appels.find(([u]) => u.includes(`/courses/${id}/`))[1];
    expect(corpsDe('merc')).toEqual({ texte: 'Remplacement', du: _merc, au: _merc });
    expect(corpsDe('dim')).toEqual({ texte: 'Remplacement', du: _dim, au: _dim });
    expect(par('cr-message-merc')).not.toBeNull();
    expect(par('cr-message-dim')).not.toBeNull();
  });

  test('V673d : une date qui n’est pas un jour du cours bloque l’enregistrement', async () => {
    await monter();
    await act(async () => { par('cr-cours-dim').querySelector('input').click(); });
    await clic(par('crm-ajouter'));
    await saisir(par('crm-texte'), 'Remplacement');
    await saisir(par('crm-du-dim'), DEMAIN);                   // un mercredi pour le dimanche
    expect(par('crm-refus').textContent).toContain('Sunday Vibes');
    expect(par('crm-enregistrer').disabled).toBe(true);
    await clic(par('crm-enregistrer'));
    expect(axios.put).not.toHaveBeenCalled();
  });

  test('V673d : en période, les vraies séances de chaque cours sont affichées', async () => {
    await monter();
    await act(async () => { par('cr-cours-dim').querySelector('input').click(); });
    await clic(par('crm-ajouter'));
    await clic(par('crm-plage'));
    await saisir(par('crm-du'), DEMAIN);
    const _au = new Date(new Date(`${DEMAIN}T00:00:00Z`).getTime() + 6 * 86400000).toISOString().slice(0, 10);
    await saisir(par('crm-au'), _au);
    expect(par('crm-seances-merc').textContent).toContain(dateLisible(DEMAIN));
    expect(par('crm-seances-dim').textContent).toContain('dimanche');
    expect(seancesDansPeriode(DIMANCHE, DEMAIN, _au)).toHaveLength(1);
    expect(seancesDansPeriode({ weekday: 0, dates_annulees: [DIM_D] }, DIM_D, DIM_D)).toHaveLength(0);
    expect(seancesDansPeriode({ name: 'sans jour' }, DEMAIN, _au)).toBeNull();
  });

  test('modification puis retrait d’un message existant', async () => {
    const AVEC = { ...MERCREDI, message_exceptionnel: { texte: 'Ancien', du: DEMAIN, au: DEMAIN } };
    await monter([AVEC, DIMANCHE]);
    expect(par('crm-existant-merc').textContent).toContain('Ancien');
    await clic(par('crm-modifier-merc'));
    expect(par('crm-texte').value).toBe('Ancien');
    await clic(par('crm-annuler'));
    axios.delete.mockResolvedValue({ data: { message_exceptionnel: null } });
    await clic(par('crm-retirer-merc'));
    expect(axios.delete).toHaveBeenCalledTimes(1);
    expect(axios.delete.mock.calls[0][0]).toMatch(/\/coach\/courses\/merc\/reminder-message$/);
    expect(par('crm-existant-merc')).toBeNull();
    expect(par('cr-message-merc')).toBeNull();
  });

  // V673b — défaut Cowork : le crayon d'UN cours ne doit jamais viser les autres cochés.
  test('crayon du mercredi avec mercredi + dimanche cochés : seul le mercredi est modifié', async () => {
    const MSG_DIM = { texte: 'Message du dimanche', du: DEMAIN, au: DEMAIN };
    const AVEC = { ...MERCREDI, message_exceptionnel: { texte: 'Ancien', du: DEMAIN, au: DEMAIN } };
    const DIM_AVEC = { ...DIMANCHE, message_exceptionnel: MSG_DIM };
    await monter([AVEC, DIM_AVEC]);
    await act(async () => { par('cr-cours-dim').querySelector('input').click(); });
    expect(par('cr-cours-dim').querySelector('input').checked).toBe(true);
    await clic(par('crm-modifier-merc'));
    expect(par('crm-cible').textContent).toContain('Session Cardio');
    expect(par('crm-cible').textContent).not.toContain('Sunday Vibes');
    expect(par('crm-enregistrer').textContent).toBe('Enregistrer pour ce cours');
    expect(par('crm-muets')).toBeNull();            // l'avertissement du dimanche ne concerne pas ce cours
    await saisir(par('crm-texte'), 'Nouveau texte mercredi');
    axios.put.mockImplementation((u, c) => Promise.resolve({ data: { message_exceptionnel: c } }));
    await clic(par('crm-enregistrer'));
    expect(axios.put).toHaveBeenCalledTimes(1);
    expect(axios.put.mock.calls[0][0]).toMatch(/\/coach\/courses\/merc\/reminder-message$/);
    expect(axios.delete).not.toHaveBeenCalled();
    expect(par('crm-existant-merc').textContent).toContain('Nouveau texte mercredi');
    expect(par('crm-existant-dim').textContent).toContain('Message du dimanche');
    // après l'édition ciblée, un NOUVEAU message reprend bien tous les cours cochés
    await clic(par('crm-ajouter'));
    expect(par('crm-cible').textContent).toContain('Session Cardio');
    expect(par('crm-cible').textContent).toContain('Sunday Vibes');
    expect(par('crm-enregistrer').textContent).toContain('2 cours');
  });

  test('retrait individuel avec deux cours cochés : un seul DELETE', async () => {
    const AVEC = { ...MERCREDI, message_exceptionnel: { texte: 'A', du: DEMAIN, au: DEMAIN } };
    const DIM_AVEC = { ...DIMANCHE, message_exceptionnel: { texte: 'B', du: DEMAIN, au: DEMAIN } };
    await monter([AVEC, DIM_AVEC]);
    await act(async () => { par('cr-cours-dim').querySelector('input').click(); });
    axios.delete.mockResolvedValue({ data: { message_exceptionnel: null } });
    await clic(par('crm-retirer-merc'));
    expect(axios.delete).toHaveBeenCalledTimes(1);
    expect(axios.delete.mock.calls[0][0]).toMatch(/\/coach\/courses\/merc\/reminder-message$/);
    expect(par('crm-existant-merc')).toBeNull();
    expect(par('crm-existant-dim')).not.toBeNull();
  });

  test('refus serveur : rien ne bascule, motif affiché', async () => {
    await monter();
    await clic(par('crm-ajouter'));
    await saisir(par('crm-texte'), 'Texte');
    await saisir(par('crm-du'), DEMAIN);
    axios.put.mockRejectedValue({ response: { data: { detail: 'Cette période est déjà passée.' } } });
    await clic(par('crm-enregistrer'));
    expect(par('crm-erreur').textContent).toContain('déjà passée');
    expect(par('crm-editeur')).not.toBeNull();
    expect(par('cr-message-merc')).toBeNull();
  });

  test('compteur et limite de 600 caractères', async () => {
    await monter();
    await clic(par('crm-ajouter'));
    await saisir(par('crm-texte'), 'x'.repeat(700));
    expect(par('crm-texte').value).toHaveLength(600);
    expect(par('crm-compteur').textContent).toBe('600/600');
  });
});

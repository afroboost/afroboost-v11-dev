/**
 * V567 — SESSIONS : le coach voit ses inscrits (compteur par session, détail au clic).
 * Un visiteur ne voit rien de nouveau et ne déclenche AUCUN appel coach.
 * axios mocké : aucun réseau.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import SessionsModal from '../SessionsModal';
import { libelleInscrits, cleOccurrence } from '../coach/InscritsSession';
import { jetonCoachUtilisable } from '../../utils/jwt';

jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn() } }));
jest.mock('../../utils/jwt', () => ({ jetonCoachUtilisable: jest.fn(() => false) }));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;
beforeAll(() => { window.scrollTo = () => {}; });

const J = new Date(Date.now() + 2 * 86400000);
const p = (n) => String(n).padStart(2, '0');
const JOUR = `${J.getFullYear()}-${p(J.getMonth() + 1)}-${p(J.getDate())}`;
const occ = (course_id, name, heure) => ({ course_id, name, datetime: `${JOUR}T${heure}:00`, locationName: 'Valangines 97', recurrent: true, offers: [] });
const AGENDA = [occ('silent', 'Afroboost Silent — Session Cardio', '18:45'), occ('unite', 'Cours à l’unité', '18:45')];
const COMPTEURS = { [`silent|${JOUR}T18:45`]: { inscrits: 12, capacite: 20 }, [`unite|${JOUR}T18:45`]: { inscrits: 3, capacite: null } };
const DETAIL = {
  session: { course_id: 'silent', occurrence: `${JOUR}T18:45` }, inscrits: 12, capacite: 20, restantes: 8, complet: false,
  participants: [
    { id: 'r1', nom: 'Léa Martin', statut: 'Confirmé', places: 1, offre: 'Pulse X10', forfait: '', essai: false, paiement: 'Inclus dans le forfait', reserve_le: '2026-09-28T10:00:00', email: 'lea@exemple.test', whatsapp: '41791234567' },
    { id: 'r2', nom: 'Noé', statut: 'Confirmé', places: 1, offre: 'Essai gratuit', forfait: '', essai: true, paiement: 'Essai gratuit', reserve_le: '2026-09-29T10:00:00', email: 'noe@exemple.test', whatsapp: '' },
    { id: 'r3', nom: 'Bassi', statut: 'Confirmé', places: 2, offre: 'Pass Duo', forfait: 'Pulse X10', essai: false, paiement: 'Inclus dans le forfait', reserve_le: '2026-09-29T11:00:00', email: '', whatsapp: '' },
  ],
  annulations: [{ nom: 'Marc', places: 1, le: '2026-09-29T12:00:00' }],
  coach_nom: 'Bassi',
};

let conteneur = null; let racine = null;
const par = (id) => document.querySelector(`[data-testid="${id}"]`);
async function monter({ coach }) {
  jetonCoachUtilisable.mockReturnValue(!!coach);
  axios.get.mockReset();
  axios.get.mockImplementation((url) => {
    const u = String(url);
    if (u.endsWith('/sessions/agenda')) return Promise.resolve({ data: { occurrences: AGENDA } });
    if (u.endsWith('/coach/sessions/inscriptions')) return Promise.resolve({ data: { sessions: COMPTEURS } });
    if (u.endsWith('/coach/sessions/detail')) return Promise.resolve({ data: DETAIL });
    return Promise.reject(new Error(u));
  });
  conteneur = document.createElement('div'); document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(<SessionsModal open onClose={() => {}} courses={[]} onReserve={() => {}} />); });
  await act(async () => { for (let i = 0; i < 8; i += 1) await Promise.resolve(); });
}
afterEach(async () => { if (racine) await act(async () => racine.unmount()); if (conteneur) conteneur.remove(); racine = null; conteneur = null; });
const appels = (fin) => axios.get.mock.calls.filter((c) => String(c[0]).endsWith(fin));

describe('V567 — compteurs du coach dans Sessions', () => {
  test('visiteur : aucun appel coach, aucun badge', async () => {
    await monter({ coach: false });
    expect(appels('/coach/sessions/inscriptions')).toHaveLength(0);
    expect(par('sessions-inscrits-0')).toBeNull();
  });

  test('coach : un badge PAR SESSION — deux cours le même jour à la même heure restent séparés', async () => {
    await monter({ coach: true });
    expect(appels('/coach/sessions/inscriptions')).toHaveLength(1);
    const textes = [par('sessions-inscrits-0').textContent.trim(), par('sessions-inscrits-1').textContent.trim()];
    expect(textes).toContain('12 / 20 places');
    expect(textes).toContain('3 inscrits');
    expect(par(`sessions-jour-inscrits-${JOUR}`).textContent).toBe('15');   // indicateur discret du calendrier
  });

  test('libellés : capacité -> « X / Y places », sans -> « X inscrits », plein -> « Complet », 0 -> « 0 inscrit »', () => {
    expect(libelleInscrits(12, 20)).toBe('12 / 20 places');
    expect(libelleInscrits(12, null)).toBe('12 inscrits');
    expect(libelleInscrits(20, 20)).toBe('Complet');
    expect(libelleInscrits(0, null)).toBe('0 inscrit');
    expect(cleOccurrence('silent', new Date(2026, 9, 7, 18, 45))).toBe('silent|2026-10-07T18:45');
  });

  test('clic sur une session : 12 / 20, 8 restantes, participants, offre, essai, Pass Duo 2 places, annulations repliées', async () => {
    await monter({ coach: true });
    const i = par('sessions-inscrits-0').textContent.trim() === '12 / 20 places' ? 0 : 1;
    await act(async () => { par(`sessions-occurrence-${i}`).click(); });
    await act(async () => { for (let k = 0; k < 8; k += 1) await Promise.resolve(); });
    const [, cfg] = appels('/coach/sessions/detail')[0];
    expect(cfg.params).toEqual({ course_id: 'silent', occurrence: `${JOUR}T18:45` });   // l'identifiant réel de la session
    expect(par('inscrits-total').textContent).toContain('12 / 20 places');
    expect(par('inscrits-restantes').textContent).toBe('8 places restantes');
    expect(par('inscrit-infos-r1').textContent).toContain('Pulse X10');
    expect(par('inscrit-essai-r2').textContent).toBe('ESSAI');
    expect(par('inscrit-essai-r1')).toBeNull();
    expect(par('inscrit-infos-r3').textContent).toContain('2 places');
    expect(par('inscrit-infos-r3').textContent).toContain('Pass Duo');
    expect(par('inscrits-annulations')).toBeNull();
    expect(par('inscrits-annulations-toggle').textContent).toContain('Annulations (1)');
    await act(async () => { par('inscrits-annulations-toggle').click(); });
    expect(par('inscrits-annulations').textContent).toContain('Marc');
    // V568 : e-mail visible d'emblée + bouton WhatsApp (plus de « Voir le contact »)
    expect(par('inscrit-voir-contact-r1')).toBeNull();
    expect(par('inscrit-contact-r1').textContent).toContain('lea@exemple.test');
  });

  test('mobile : liste en une colonne rétrécissable, textes qui passent à la ligne', async () => {
    await monter({ coach: true });
    await act(async () => { par('sessions-occurrence-0').click(); });
    await act(async () => { for (let k = 0; k < 8; k += 1) await Promise.resolve(); });
    expect(par('inscrits-liste').style.gridTemplateColumns).toBe('minmax(0, 1fr)');
    expect(par('inscrit-infos-r1').style.overflowWrap).toBe('anywhere');
  });
});

describe('V568 — WhatsApp dans le détail des inscrits', () => {
  const ouvrirDetail = async () => {
    await monter({ coach: true });
    const i = par('sessions-inscrits-0').textContent.trim() === '12 / 20 places' ? 0 : 1;
    await act(async () => { par(`sessions-occurrence-${i}`).click(); });
    await act(async () => { for (let k = 0; k < 8; k += 1) await Promise.resolve(); });
  };

  test('numéro connu -> bouton WhatsApp : wa.me/<numéro> + message prérempli (prénom, coach, date, heure)', async () => {
    await ouvrirDetail();
    const a = par('inscrit-whatsapp-r1');
    expect(a).not.toBeNull();
    expect(a.tagName).toBe('A');
    const url = new URL(a.getAttribute('href'));
    expect(url.origin + url.pathname).toBe('https://wa.me/41791234567');
    const texte = url.searchParams.get('text');
    expect(texte).toContain('Bonjour Léa');
    expect(texte).toContain('Bassi d’Afroboost');
    expect(texte).toContain('18h45');
    const [a2, m2, j2] = [J.getFullYear(), J.getMonth(), J.getDate()];
    expect(texte).toContain(new Date(a2, m2, j2).toLocaleDateString('fr-CH', { weekday: 'long', day: 'numeric', month: 'long' }));
    expect(a.getAttribute('target')).toBe('_blank');            // WhatsApp s'ouvre : rien n'est envoyé d'ici
    expect(axios.get.mock.calls.every((c) => !/whatsapp|send/i.test(String(c[0])))).toBe(true);
  });

  test('sans numéro -> « WhatsApp non renseigné », aucun lien cassé ; l’e-mail reste', async () => {
    await ouvrirDetail();
    expect(par('inscrit-whatsapp-r2')).toBeNull();
    expect(par('inscrit-sans-whatsapp-r2').textContent).toBe('WhatsApp non renseigné');
    expect(par('inscrit-contact-r2').textContent).toContain('noe@exemple.test');
    expect(document.querySelectorAll('a[href^="https://wa.me/?"]')).toHaveLength(0);   // jamais de wa.me sans numéro
  });

  test('Pass Duo : chaque billet garde SON contact (aucun numéro emprunté)', async () => {
    await ouvrirDetail();
    expect(par('inscrit-whatsapp-r3')).toBeNull();            // r3 n'a pas de numéro : pas celui de r1
    expect(par('inscrit-sans-whatsapp-r3')).not.toBeNull();
  });
});

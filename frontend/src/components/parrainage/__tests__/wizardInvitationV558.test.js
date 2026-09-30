/**
 * V558 — WIZARD « INVITATION & PARRAINAGE » : Offre · Séance · Ta carte · Partage.
 *
 * axios est mocké : aucun réseau. Le calendrier est le SessionsModal EXISTANT,
 * alimenté par les seules séances renvoyées par le serveur (GET /chain/options).
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import InvitationDuo from '../InvitationDuo';
import { MESSAGE_CHAINE_DEFAUT, cleChaine, _resetParrainagePourTest, seancesPourCalendrier } from '../../../utils/parrainage';

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), patch: jest.fn(), delete: jest.fn() },
}));
jest.mock('qrcode.react', () => ({
  QRCodeSVG: (p) => <svg data-testid="qr-svg" data-value={p.value} />,
  QRCodeCanvas: (p) => <canvas data-testid="qr-canvas" data-value={p.value} />,
}));

let conteneur, racine;
beforeEach(() => {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  jest.clearAllMocks();
  axios.get.mockReset(); axios.post.mockReset(); axios.patch.mockReset();
  window.localStorage.clear();
  _resetParrainagePourTest();
  global.fetch = undefined;
  window.open = jest.fn(() => null);
  window.scrollTo = jest.fn(); // jsdom : le calendrier restaure la position de défilement
});
afterEach(() => {
  if (racine) act(() => racine.unmount());
  racine = null;
  conteneur.remove();
});

const par = (id) => document.querySelector(`[data-testid="${id}"]`);
const vider = () => act(async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); });
async function monter(element) {
  await act(async () => { racine = createRoot(conteneur); racine.render(element); });
  await vider();
}
const cliquer = async (id) => { await act(async () => { par(id).click(); }); await vider(); };
// Le calendrier se ferme puis transmet la séance 60 ms plus tard (SessionsModal) : on attend.
const choisirCetteSeance = async () => {
  await cliquer('sessions-reserver');
  await act(async () => { await new Promise((r) => setTimeout(r, 80)); });
  await vider();
};

const pad = (n) => String(n).padStart(2, '0');
const demain = new Date(Date.now() + 86400000);
const O2 = `${demain.getFullYear()}-${pad(demain.getMonth() + 1)}-${pad(demain.getDate())}T18:45:00`;
const CLE_JOUR = O2.slice(0, 10);
const COURSE = { id: 'c1', name: 'Afroboost Dimanche', time: '18:30', locationName: 'Bord du Lac, Auvernier' };
const OCC = '2026-09-27T18:30:00';
const PUB = { status: 'waiting', sponsor_first_name: 'Henri', course: COURSE, occurrence: OCC, expired: false, version: 1,
  chain_required: true, chain: { exists: false, shared: false }, invitation_type: 'trial' };
const OPTS = {
  types: [
    { id: 'trial', libelle: 'Essai gratuit', texte: 'Offre à ton ami son premier cours Afroboost.', nature: 'premier_essai', recompense: null },
    { id: 'parrainage', libelle: 'Parrainage', texte: 'Invite un ami et profite de l’avantage prévu par ton programme.',
      nature: 'recompense_parrainage', recompense: 'Tu gagnes 1 séance offerte de parrainage quand les conditions sont remplies.' },
  ],
  seances: [{ course_id: 'c2', name: 'Afroboost Silent – Session Cardio', location: 'Ch. des Valangines 97, 2000 Neuchâtel',
    time: '18:45', occurrences: [O2] }],
  seance_parent: { course_id: 'c1', occurrence: OCC },
};
const CHILD = (extra) => Object.assign({
  share_token: 'T1', share_url: 'https://afroboost.com/api/share/duo/T1?v=3',
  invite_url: 'https://afroboost.com/duo/T1', card_url: 'https://afroboost.com/api/share/duo/T1/carte.jpg?v=h1',
  display_name: null, message: MESSAGE_CHAINE_DEFAUT, occurrence: O2, kind: 'parrainage', seance_choisie: true, shared: false,
  course: { name: 'Afroboost Silent – Session Cardio', time: '18:45', locationName: 'Ch. des Valangines 97, 2000 Neuchâtel' },
  inviter_display: { prenom: null, photo_url: null },
}, extra || {});

function routerGet({ options } = {}) {
  axios.get.mockImplementation((url) => {
    if (String(url).endsWith('/chain/options')) return options ? options() : Promise.resolve({ data: OPTS });
    return Promise.resolve({ data: PUB });
  });
}
function routerPost({ chain } = {}) {
  axios.post.mockImplementation((url) => {
    const u = String(url);
    if (u.endsWith('/chain')) return chain ? chain() : Promise.resolve({ status: 201, data: { child: CHILD(), edit_key: 'K1', shared: false, preview: { ok: true } } });
    if (u.endsWith('/chain/share')) return Promise.resolve({ data: { shared: true, child: CHILD({ shared: true }) } });
    return Promise.reject(new Error(`inattendu ${u}`));
  });
}
async function choisirDansLeCalendrier() {
  await cliquer('wf-seance-choisir');
  expect(par('sessions-modal')).not.toBeNull();
  if (!par(`sessions-jour-${CLE_JOUR}`)) await cliquer('sessions-mois-suivant');
  await cliquer(`sessions-jour-${CLE_JOUR}`);
  await cliquer('sessions-occurrence-0');
  expect(par('sessions-reserver').textContent).toBe('Choisir cette séance');
  await choisirCetteSeance();
}

describe('V558 — Wizard 4 étapes', () => {
  test('stepper Offre / Séance / Ta carte / Partage ; étape 1 = seulement les offres autorisées, avec la récompense', async () => {
    routerGet(); routerPost();
    await monter(<InvitationDuo token="T0" />);
    expect(par('wf-etapes').textContent.replace(/\s+/g, '')).toBe('1Offre2Séance3Tacarte4Partage');
    expect(par('wf-offre-titre').textContent).toBe('Que veux-tu partager ?');
    expect(par('wf-offre-trial').getAttribute('aria-checked')).toBe('true');       // premier type par défaut
    expect(par('wf-offre-parrainage').getAttribute('aria-checked')).toBe('false');
    expect(par('wf-offre-affiliation')).toBeNull();                                  // aucun programme : masquée
    expect(par('wf-recompense-parrainage').textContent).toContain('séance offerte de parrainage');
    expect(par('wf-regle-essai').textContent).toContain('une seule fois par personne');
    expect(conteneur.textContent).not.toContain('Ton premier cours est offert');
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('offre + séance choisies dans le calendrier EXISTANT → résumé compact → POST /chain les porte (enfant créé APRÈS la séance)', async () => {
    routerGet(); routerPost();
    await monter(<InvitationDuo token="T0" />);
    await cliquer('wf-offre-parrainage');
    expect(par('wf-offre-parrainage').getAttribute('aria-checked')).toBe('true');
    await cliquer('wf-continuer');
    expect(par('wf-seance-titre').textContent).toBe('Choisis la séance de ton ami');
    expect(par('wf-seance-continuer').disabled).toBe(true);                          // séance obligatoire
    await choisirDansLeCalendrier();
    expect(par('sessions-modal')).toBeNull();                                         // le calendrier se ferme
    const resume = par('wf-seance-resume');
    expect(resume.textContent).toContain('Séance choisie');
    expect(resume.textContent).toContain('18:45');
    expect(resume.textContent).toContain('Afroboost Silent – Session Cardio');
    expect(resume.textContent).toContain('Ch. des Valangines 97, 2000 Neuchâtel');
    expect(par('wf-seance-changer')).not.toBeNull();
    expect(axios.post).not.toHaveBeenCalled();
    await cliquer('wf-seance-continuer');
    const creation = axios.post.mock.calls.find((c) => String(c[0]).endsWith('/chain'));
    expect(creation[1]).toEqual(expect.objectContaining({ kind: 'parrainage', course_id: 'c2', occurrence: O2 }));
    expect(par('wf-etape-carte')).not.toBeNull();
    expect(par('wf-apercu').querySelector('[data-testid="carte-invitation-type"]').textContent).toBe('Parrainage');
    expect(par('wf-apercu').textContent).toContain('Afroboost Silent – Session Cardio');
    expect(window.localStorage.getItem(cleChaine('T0'))).toBe('K1');
  });

  test('séance devenue indisponible → retour à « Séance », message clair, « Choisir une autre séance », jamais de bascule silencieuse', async () => {
    routerGet();
    routerPost({ chain: () => Promise.reject({ response: { status: 400, headers: { 'x-refus-raison': 'seance_indisponible' }, data: {} } }) });
    await monter(<InvitationDuo token="T0" />);
    await cliquer('wf-continuer');
    await choisirDansLeCalendrier();
    await cliquer('wf-seance-continuer');
    expect(par('wf-etape-2')).not.toBeNull();
    expect(par('wf-seance-erreur').textContent).toBe('Cette séance n’est plus disponible.');
    expect(par('wf-seance-autre')).not.toBeNull();
    expect(par('wf-seance-continuer').disabled).toBe(true);
    expect(axios.post.mock.calls.filter((c) => String(c[0]).endsWith('/chain')).length).toBe(1);
    await cliquer('wf-seance-autre');
    expect(par('sessions-modal')).not.toBeNull();
  });

  test('retour à « Séance » après création : « Changer de séance » → PATCH (clé de l’appareil), le parent n’est jamais touché', async () => {
    const O3 = `${O2.slice(0, 10)}T20:00:00`;
    routerGet({ options: () => Promise.resolve({ data: Object.assign({}, OPTS, { seances: [
      Object.assign({}, OPTS.seances[0], { occurrences: [O2, O3] })] }) }) });
    routerPost();
    axios.patch.mockResolvedValue({ data: { child: CHILD({ occurrence: O3 }), preview: { ok: true } } });
    await monter(<InvitationDuo token="T0" />);
    await cliquer('wf-continuer');
    await choisirDansLeCalendrier();
    await cliquer('wf-seance-continuer');
    await cliquer('wf-retour');
    expect(par('wf-etape-2')).not.toBeNull();
    await cliquer('wf-seance-changer');
    if (!par(`sessions-jour-${CLE_JOUR}`)) await cliquer('sessions-mois-suivant');
    await cliquer(`sessions-jour-${CLE_JOUR}`);
    await cliquer('sessions-occurrence-1');
    await choisirCetteSeance();
    await cliquer('wf-seance-continuer');
    const patch = axios.patch.mock.calls[0];
    expect(patch[1]).toEqual({ course_id: 'c2', occurrence: O3 });
    expect(patch[2].headers).toEqual({ 'X-Chain-Key': 'K1' });
    expect(par('wf-etape-carte')).not.toBeNull();
    expect(axios.post.mock.calls.filter((c) => String(c[0]).endsWith('/chain')).length).toBe(1);
  });

  test('options indisponibles → l’ami est invité à TA séance, le parcours continue (aucune séance inventée)', async () => {
    routerGet({ options: () => Promise.reject({ response: { status: 500 } }) });
    routerPost();
    await monter(<InvitationDuo token="T0" />);
    expect(par('wf-offre-trial')).not.toBeNull();       // repli : le type du pass seul
    expect(par('wf-offre-parrainage')).toBeNull();
    await cliquer('wf-continuer');
    expect(par('wf-seance-meme').textContent).toContain('Ton ami est invité à la même séance que toi');
    await cliquer('wf-seance-continuer');
    const creation = axios.post.mock.calls.find((c) => String(c[0]).endsWith('/chain'));
    expect(creation[1].course_id).toBeUndefined();
    expect(creation[1].occurrence).toBeUndefined();
  });

  test('seancesPourCalendrier : une entrée par date, cours / lieu / id du cours', () => {
    const o = seancesPourCalendrier(OPTS.seances);
    expect(o).toHaveLength(1);
    expect(o[0]).toEqual(expect.objectContaining({ id: 'c2', nom: 'Afroboost Silent – Session Cardio',
      lieu: 'Ch. des Valangines 97, 2000 Neuchâtel', iso: O2 }));
    expect(seancesPourCalendrier(null)).toEqual([]);
  });
});

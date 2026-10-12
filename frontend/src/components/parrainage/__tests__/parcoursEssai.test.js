/**
 * V607 — ESSAI GRATUIT « MOI D'ABORD → PUIS MON AMI ».
 *
 * axios et fetch sont mockés : aucun réseau. Le calendrier est le SessionsModal
 * EXISTANT, alimenté par les seules séances du serveur (GET /chain/options).
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import InvitationDuo from '../InvitationDuo';
import { cleChaine, _resetParrainagePourTest, texteWhatsAppEssai, estParcoursEssai } from '../../../utils/parrainage';

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
  global.fetch = jest.fn(() => Promise.resolve({ ok: true }));
  window.open = jest.fn(() => null);
  window.scrollTo = jest.fn();
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
const saisir = (id, v) => act(async () => {
  const el = par(id);
  Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(el, v);
  el.dispatchEvent(new Event('input', { bubbles: true }));
});
const evenementsSuivis = () => global.fetch.mock.calls
  .filter((c) => String(c[0]).endsWith('/api/invitation/suivi'))
  .map((c) => JSON.parse(c[1].body).evenement);

const pad = (n) => String(n).padStart(2, '0');
const isoJour = (d, h) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${h}:00`;
const dans = (j) => new Date(Date.now() + j * 86400000);
// Le prochain dimanche (getDay() === 0), au moins demain.
const DIM = (() => { let d = dans(1); while (d.getDay() !== 0) d = new Date(d.getTime() + 86400000); return d; })();
const O_DIM = isoJour(DIM, '18:00');
const O_MER = isoJour(dans(2), '18:30');
const COURSE = { id: 'c-mer', name: 'Cours à l’unité', time: '18:30', locationName: 'Valangines, Neuchâtel' };
const PUB = {
  status: 'waiting', inviter_display: { prenom: 'Coach Bassi', source: 'coach' }, course: COURSE, occurrence: O_MER,
  expired: false, version: 1, chain_required: true, chain: { exists: false, shared: false }, invitation_type: 'trial',
};
const OPTS = {
  types: [{ id: 'trial', libelle: 'Essai gratuit', texte: 'x', nature: 'premier_essai', recompense: null }],
  seances: [
    { course_id: 'c-mer', name: 'Cours à l’unité', location: 'Valangines, Neuchâtel', time: '18:30', occurrences: [O_MER] },
    { course_id: 'c-dim', name: 'Cours à l’unité', location: 'Bord du Lac, Auvernier', time: '18:00', occurrences: [O_DIM] },
  ],
};
const CHILD = (extra) => Object.assign({
  share_token: 'T1', share_url: 'https://afroboost.com/api/share/duo/T1?v=1', display_name: null,
  message: 'Je t’invite', occurrence: O_DIM, kind: 'trial', seance_choisie: false, shared: false,
  course: { name: 'Cours à l’unité', time: '18:00', locationName: 'Bord du Lac, Auvernier' },
}, extra || {});

function routeur({ join, chainPost } = {}) {
  axios.get.mockImplementation((url) => {
    if (String(url).endsWith('/chain/options')) return Promise.resolve({ data: OPTS });
    return Promise.resolve({ data: PUB });
  });
  axios.patch.mockImplementation((url, corps) => {
    const u = String(url);
    if (u.endsWith('/occurrence')) {
      return Promise.resolve({ data: Object.assign({}, PUB, { occurrence: corps.occurrence, version: 2,
        course: { id: 'c-dim', name: 'Cours à l’unité', time: '18:00', locationName: 'Bord du Lac, Auvernier' } }) });
    }
    if (u.endsWith('/chain')) return Promise.resolve({ data: { child: CHILD({ display_name: corps.display_name }) } });
    return Promise.reject(new Error(`inattendu ${u}`));
  });
  axios.post.mockImplementation((url) => {
    const u = String(url);
    if (u.endsWith('/chain')) return chainPost ? chainPost() : Promise.resolve({ status: 201, data: { child: CHILD(), edit_key: 'K1', shared: false } });
    if (u.endsWith('/chain/share')) return Promise.resolve({ data: { shared: true, child: CHILD({ shared: true, share_url: 'https://afroboost.com/api/share/duo/T1?v=2' }) } });
    if (u.endsWith('/join')) return join ? join() : Promise.resolve({ data: { status: 'unlocked', occurrence: O_DIM,
      course: { name: 'Cours à l’unité', locationName: 'Bord du Lac, Auvernier' },
      tickets: [{ role: 'invitee', first_name: 'Aminata', reservationCode: 'AF1', qr_value: 'https://afroboost.com/validate/AF1?res=1' }] } });
    return Promise.reject(new Error(`inattendu ${u}`));
  });
}

async function choisirDimanche() {
  await cliquer('wf-ma-seance-changer');
  expect(par('sessions-modal')).not.toBeNull();
  const cle = O_DIM.slice(0, 10);
  if (!par(`sessions-jour-${cle}`)) await cliquer('sessions-mois-suivant');
  await cliquer(`sessions-jour-${cle}`);
  await cliquer('sessions-occurrence-0');
  await cliquer('sessions-reserver');
  await act(async () => { await new Promise((r) => setTimeout(r, 80)); });
  await vider();
}

async function jusquAuPartage() {
  await monter(<InvitationDuo token="T0" />);
  await choisirDimanche();
  await cliquer('wf-valider-seance');
}

describe('V607 — Essai gratuit : moi d’abord, puis mon ami', () => {
  test('accueil : qui m’invite, Afroboost, la séance proposée, « premier cours offert » ; jamais « Pass Duo » ; aucune création avant mon choix', async () => {
    routeur();
    await monter(<InvitationDuo token="T0" />);
    expect(par('wf-essai-accueil')).not.toBeNull();
    expect(par('invitation-pill').textContent).toBe('Essai gratuit');
    expect(par('carte-invitation-titre').textContent).toBe('Coach Bassi t’invite à découvrir Afroboost');
    expect(par('carte-invitation-type').textContent).toBe('Essai gratuit');
    expect(par('wf-pitch').textContent).toContain('Cardio + danse afro + casques immersifs');
    expect(par('wf-pitch').textContent).toContain('1 h');
    expect(par('wf-offert').textContent.trim()).toBe('Ton premier cours est offert.');
    expect(par('wf-invitation-recue').textContent).toContain('Valangines, Neuchâtel');
    expect(conteneur.textContent).not.toContain('Pass Duo');
    expect(par('wf-seance-titre')).toBeNull();                 // plus de « séance de ton ami » au départ
    expect(par('wf-etapes')).toBeNull();
    expect(axios.post).not.toHaveBeenCalled();
    expect(evenementsSuivis()).toEqual(['lien_ouvert']);
  });

  test('je choisis MA séance (dimanche) → PATCH /occurrence avec le cours ; puis « Ton essai est prêt » ; l’invitation de l’ami hérite de ma séance', async () => {
    routeur();
    await monter(<InvitationDuo token="T0" />);
    await choisirDimanche();
    expect(par('wf-invitation-recue').textContent).toContain('Bord du Lac, Auvernier');   // aperçu local avant validation
    expect(axios.patch).not.toHaveBeenCalled();
    await cliquer('wf-valider-seance');
    const patch = axios.patch.mock.calls[0];
    expect(String(patch[0])).toMatch(/\/pass\/T0\/occurrence$/);
    expect(patch[1]).toEqual({ occurrence: O_DIM, version: 1, course_id: 'c-dim' });
    expect(par('wf-essai-pret')).not.toBeNull();
    expect(par('wf-essai-pret').textContent).toContain('Ton essai est prêt !');
    expect(par('wf-essai-pret-texte').textContent).toBe('Pour le débloquer, invite à ton tour une personne à découvrir Afroboost.');
    expect(par('wf-texte-lien').textContent).toBe('Ton ami recevra son propre lien d’invitation.');
    expect(par('wf-rappel-seance').textContent).toContain('Bord du Lac, Auvernier');
    const creation = axios.post.mock.calls.find((c) => String(c[0]).endsWith('/chain'));
    expect(creation[1].course_id).toBeUndefined();          // pas de séance de l'ami demandée
    expect(creation[1].occurrence).toBeUndefined();
    expect(window.localStorage.getItem(cleChaine('T0'))).toBe('K1');
    expect(par('wf-finaliser').disabled).toBe(true);       // bloqué tant que rien n'est partagé
    expect(evenementsSuivis()).toEqual(['lien_ouvert', 'seance_choisie', 'etape_invitation_atteinte']);
  });

  test('« Inviter 1 ami sur WhatsApp » ouvre WhatsApp (message + lien) DANS le geste, enregistre le partage, débloque « Finaliser »', async () => {
    routeur();
    await jusquAuPartage();
    await cliquer('wf-inviter-whatsapp');
    expect(window.open).toHaveBeenCalledTimes(1);
    const lien = decodeURIComponent(String(window.open.mock.calls[0][0]).split('?text=')[1]);
    expect(lien).toContain('t’invite à découvrir Afroboost !');
    expect(lien).toContain('🎧 Cardio + danse afro + casques immersifs');
    expect(lien).toContain('📍 Bord du Lac, Auvernier');
    expect(lien).toContain('🎁 Ton premier cours est offert.');
    expect(lien).toContain('https://afroboost.com/api/share/duo/T1?v=1');
    const share = axios.post.mock.calls.find((c) => String(c[0]).endsWith('/chain/share'));
    expect(share[1]).toEqual({ channel: 'whatsapp' });
    expect(share[2].headers).toEqual({ 'X-Chain-Key': 'K1' });
    expect(par('wf-partage-ok').textContent).toContain('Invitation partagée');
    expect(conteneur.textContent).not.toMatch(/envoy[ée]/i);
    expect(par('wf-finaliser').disabled).toBe(false);
    expect(evenementsSuivis()).toContain('partage_whatsapp_declenche');
  });

  test('prénom saisi : enregistré sur la carte de l’ami AVANT le partage (fenêtre ouverte dans le geste, adresse posée après)', async () => {
    routeur();
    const fen = { location: { href: '' }, opener: {}, close: jest.fn() };
    window.open = jest.fn(() => fen);
    await jusquAuPartage();
    await saisir('wf-nom', 'Aminata');
    await cliquer('wf-inviter-whatsapp');
    expect(window.open.mock.calls[0][0]).toBe('');
    const patch = axios.patch.mock.calls.find((c) => String(c[0]).endsWith('/chain'));
    expect(patch[1]).toEqual(expect.objectContaining({ display_name: 'Aminata' }));
    expect(decodeURIComponent(fen.location.href)).toContain('🔥 Aminata t’invite à découvrir Afroboost !');
    expect(fen.opener).toBeNull();
    expect(par('wf-finaliser').disabled).toBe(false);
  });

  test('après le partage : formulaire existant → « Ton essai est confirmé ! » (date, lieu, billet) + « Inviter encore » facultatif', async () => {
    routeur();
    await jusquAuPartage();
    await cliquer('wf-inviter-whatsapp');
    await cliquer('wf-finaliser');
    expect(par('wf-inscription')).not.toBeNull();
    await saisir('invitation-prenom', 'Aminata');
    await saisir('invitation-email', 'aminata@example.com');
    await saisir('invitation-whatsapp', '+41 79 000 00 00');
    await act(async () => { par('invitation-consent').click(); });
    await cliquer('invitation-rejoindre');
    expect(axios.post.mock.calls.find((c) => String(c[0]).endsWith('/join'))[2].headers).toEqual({ 'X-Chain-Key': 'K1' });
    expect(evenementsSuivis()).toContain('reservation_commencee');
    const ok = par('wf-essai-confirme');
    expect(ok).not.toBeNull();
    expect(ok.textContent).toContain('Ton essai est confirmé');
    expect(par('wf-essai-confirme-seance').textContent).toContain('Bord du Lac, Auvernier');
    expect(par('wf-essai-confirme-seance').textContent).toContain('18:00');
    expect(document.querySelectorAll('[data-testid="qr-svg"]')).toHaveLength(1);
    expect(ok.textContent).toContain('Tu peux inviter d’autres amis si tu veux.');
    expect(conteneur.textContent).not.toContain('Pass Duo');
    window.open.mockClear();
    await cliquer('wf-inviter-encore');
    expect(window.open).toHaveBeenCalledTimes(1);
    expect(decodeURIComponent(String(window.open.mock.calls[0][0]))).toContain('https://afroboost.com/api/share/duo/T1?v=2');
  });

  test('le serveur garde l’obligation : 409 invitation_requise au join → retour à « Essai prêt », « Finaliser » rebloqué', async () => {
    routeur({ join: () => Promise.reject({ response: { status: 409, headers: { 'x-refus-raison': 'invitation_requise' }, data: {} } }) });
    await jusquAuPartage();
    await cliquer('wf-inviter-whatsapp');
    await cliquer('wf-finaliser');
    await saisir('invitation-prenom', 'Aminata');
    await saisir('invitation-email', 'aminata@example.com');
    await saisir('invitation-whatsapp', '+41 79 000 00 00');
    await act(async () => { par('invitation-consent').click(); });
    await cliquer('invitation-rejoindre');
    expect(par('wf-essai-pret')).not.toBeNull();
    expect(par('wf-avis').textContent).toBe("Invite d'abord un ami pour débloquer ton essai gratuit.");
    expect(par('wf-finaliser').disabled).toBe(true);
  });

  test('séance refusée par le serveur → message clair, on reste sur l’accueil (aucune bascule silencieuse)', async () => {
    routeur();
    axios.patch.mockImplementation(() => Promise.reject({ response: { status: 400, headers: { 'x-refus-raison': 'seance_indisponible' }, data: {} } }));
    await monter(<InvitationDuo token="T0" />);
    await choisirDimanche();
    await cliquer('wf-valider-seance');
    expect(par('wf-essai-accueil')).not.toBeNull();
    expect(par('wf-seance-erreur').textContent).toBe('Cette séance n’est plus disponible.');
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('Pass Duo : le parcours « venir avec un ami » est inchangé et n’affiche jamais « Essai gratuit » comme type', async () => {
    axios.get.mockImplementation((url) => (String(url).endsWith('/chain/options')
      ? Promise.resolve({ data: { types: [{ id: 'pass_duo', libelle: 'Pass Duo', texte: 'x' }], seances: [] } })
      : Promise.resolve({ data: Object.assign({}, PUB, { invitation_type: 'pass_duo' }) })));
    axios.post.mockImplementation(() => Promise.resolve({ status: 201, data: { child: CHILD({ kind: 'pass_duo' }), edit_key: 'K1' } }));
    await monter(<InvitationDuo token="T0" />);
    expect(par('wf-essai-accueil')).toBeNull();
    expect(par('wf-etapes')).not.toBeNull();                  // le Wizard Pass Duo d'avant
    expect(par('invitation-pill').textContent).toBe('Pass Duo');
    expect(par('carte-invitation-type').textContent).toBe('Pass Duo');
  });
});

describe('V607 — moteur pur', () => {
  test('texteWhatsAppEssai : message court ; un champ absent = ligne omise', () => {
    const complet = texteWhatsAppEssai({ prenom: 'Aminata', occurrence: '2026-10-18T18:00:00', lieu: 'Bord du Lac, Auvernier', url: 'https://x/T1' });
    const l = complet.split('\n');
    expect(l[0]).toBe('🔥 Aminata t’invite à découvrir Afroboost !');
    expect(l[1]).toBe('🎧 Cardio + danse afro + casques immersifs');
    expect(l[2]).toMatch(/^📅 Dimanche 18 oct/);
    expect(l[3]).toBe('⏰ 18:00');
    expect(l[4]).toBe('📍 Bord du Lac, Auvernier');
    expect(l.slice(5)).toEqual(['🎁 Ton premier cours est offert.', 'Réserve ton essai ici :', 'https://x/T1',
      'Et à ton tour, tu pourras inviter quelqu’un 💜']);
    const minimal = texteWhatsAppEssai({ url: 'https://x/T1' }).split('\n');
    expect(minimal[0]).toBe('🔥 Je t’invite à découvrir Afroboost !');
    expect(minimal.some((x) => /^📅|^⏰|^📍/.test(x))).toBe(false);
    expect(texteWhatsAppEssai({ prenom: 'a@b.ch', url: 'u' }).split('\n')[0]).toBe('🔥 Je t’invite à découvrir Afroboost !');
  });

  test('estParcoursEssai : chaîne requise ET Essai gratuit seulement', () => {
    expect(estParcoursEssai({ chain_required: true, invitation_type: 'trial' })).toBe(true);
    expect(estParcoursEssai({ chain_required: true, invitation_type: 'pass_duo' })).toBe(false);
    expect(estParcoursEssai({ chain_required: false, invitation_type: 'trial' })).toBe(false);
    expect(estParcoursEssai(null)).toBe(false);
  });
});

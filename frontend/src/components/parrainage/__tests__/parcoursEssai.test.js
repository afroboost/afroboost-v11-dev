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

function routeur({ join, chainPost, audio } = {}) {
  axios.get.mockImplementation((url) => {
    if (String(url).endsWith('/chain/options')) return Promise.resolve({ data: OPTS });
    return Promise.resolve({ data: audio ? Object.assign({}, PUB, { audio_url: audio }) : PUB });
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
    if (u.endsWith('/chain/next')) {
      const n = axios.post.mock.calls.filter((c) => String(c[0]).endsWith('/chain/next')).length;
      return Promise.resolve({ status: 201, data: { child: CHILD({ share_token: `T${n + 1}`, share_url: `https://afroboost.com/api/share/duo/T${n + 1}?v=0` }) } });
    }
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
  await choisirDimanche();               // V610k : choisir dans le calendrier VALIDE directement
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
    // V610k : « Valider ma séance » dans le calendrier -> directement « Ton essai est prêt »
    // (plus de retour à l'accueil pour revalider).
    expect(par('wf-essai-accueil')).toBeNull();
    const patch = axios.patch.mock.calls[0];
    expect(String(patch[0])).toMatch(/\/pass\/T0\/occurrence$/);
    expect(patch[1]).toEqual({ occurrence: O_DIM, version: 1, course_id: 'c-dim' });
    expect(par('wf-essai-pret')).not.toBeNull();
    expect(par('wf-essai-pret').textContent).toContain('Ton essai est prêt !');
    expect(par('wf-essai-pret-texte').textContent).toBe('Pour confirmer ton essai gratuit, invite 1 ami à découvrir Afroboost.');
    expect(par('wf-inviter-whatsapp').textContent).toContain('Inviter 1 ami et confirmer ma place');
    expect(par('wf-texte-lien').textContent).toBe('Ton ami recevra son propre lien d’invitation.');
    expect(par('wf-rappel-seance').textContent).toContain('Bord du Lac, Auvernier');
    const creation = axios.post.mock.calls.find((c) => String(c[0]).endsWith('/chain'));
    expect(creation[1].course_id).toBeUndefined();          // pas de séance de l'ami demandée
    expect(creation[1].occurrence).toBeUndefined();
    expect(window.localStorage.getItem(cleChaine('T0'))).toBe('K1');
    expect(par('wf-finaliser')).toBeNull();                // V610l : plus de « Finaliser mon inscription »
    expect(conteneur.textContent).not.toContain('Finaliser');
    expect(axios.post.mock.calls.find((c) => String(c[0]).endsWith('/join'))).toBeUndefined();
    expect(evenementsSuivis()).toEqual(['lien_ouvert', 'seance_choisie', 'etape_invitation_atteinte']);
  });

  // ── V610l : un clic = prénom → partage → place confirmée → WhatsApp ──────
  const fenetre = () => ({ location: { href: '' }, opener: {}, close: jest.fn() });
  async function coordonnees(prenom) {
    await saisir('wf-nom', prenom || 'Aminata');
    await saisir('wf-email', 'aminata@example.com');
    await saisir('wf-whatsapp', '+41 79 000 00 00');
    await act(async () => { par('wf-consent').click(); });
  }
  const appels = (fin) => axios.post.mock.calls.filter((c) => String(c[0]).endsWith(fin));
  async function confirmerPlace(prenom) {
    const fen = fenetre();
    window.open = jest.fn(() => fen);
    await jusquAuPartage();
    await coordonnees(prenom);
    await cliquer('wf-inviter-whatsapp');
    return fen;
  }

  test('E/F/G/H — « Inviter 1 ami et confirmer ma place » : partage enregistré PUIS place confirmée PUIS WhatsApp ; aucun retour nécessaire', async () => {
    routeur();
    const fen = await confirmerPlace('Aminata');
    expect(window.open).toHaveBeenCalledTimes(1);
    expect(window.open.mock.calls[0][0]).toBe('');               // fenêtre ouverte DANS le geste
    expect(fen.opener).toBeNull();
    // V618k — ordre serveur : prénom (PATCH /chain) → POST /join portant le canal ; le serveur
    // n'écrit le partage qu'APRÈS avoir accordé l'essai (plus de POST /chain/share avant).
    expect(axios.patch.mock.calls.find((c) => String(c[0]).endsWith('/chain'))[1]).toEqual(expect.objectContaining({ display_name: 'Aminata' }));
    expect(appels('/chain/share')).toHaveLength(0);
    const join = appels('/join')[0];
    expect(join[1]).toEqual(expect.objectContaining({ name: 'Aminata', email: 'aminata@example.com', whatsapp: '+41 79 000 00 00',
      consent_reservation: true, terms_accepted: true, marketing_consent: false, partage_canal: 'whatsapp' }));
    expect(join[2].headers).toEqual({ 'X-Chain-Key': 'K1' });
    // WhatsApp : message + lien PERSONNEL de l'ami, posé APRÈS la confirmation
    const lien = decodeURIComponent(fen.location.href);
    expect(lien).toContain('🔥 Aminata t’invite à découvrir Afroboost !');
    expect(lien).toContain('🎁 Ton premier cours est offert.');
    expect(lien).toContain('https://afroboost.com/api/share/duo/T1');
    // la place est réservée, sans aucun autre geste
    const ok = par('wf-essai-confirme');
    expect(ok).not.toBeNull();
    expect(ok.textContent).toContain('Ta place est réservée');
    expect(par('wf-confirme-texte').textContent).toBe('Ton invitation personnelle est prête. Partage-la maintenant avec ton ami.');
    expect(par('wf-essai-confirme-seance').textContent).toContain('Bord du Lac, Auvernier');
    expect(document.querySelectorAll('[data-testid="qr-svg"]')).toHaveLength(1);
    expect(par('wf-finaliser')).toBeNull();
    expect(conteneur.textContent).not.toMatch(/envoy[ée]/i);       // jamais « envoyé »
    expect(evenementsSuivis()).toEqual(expect.arrayContaining(['reservation_commencee', 'partage_whatsapp_declenche']));
    expect(par('wf-whatsapp-bloque')).toBeNull();
  });

  test('coordonnées incomplètes : rien n’est ouvert, rien n’est envoyé', async () => {
    routeur();
    await jusquAuPartage();
    await saisir('wf-nom', 'Aminata');
    await cliquer('wf-inviter-whatsapp');
    expect(par('wf-erreur-form').textContent).toBe('Indique une adresse e-mail valide.');
    expect(window.open).not.toHaveBeenCalled();
    expect(appels('/chain/share')).toHaveLength(0);
    expect(appels('/join')).toHaveLength(0);
    await saisir('wf-email', 'aminata@example.com');
    await saisir('wf-whatsapp', '+41 79 000 00 00');
    await cliquer('wf-inviter-whatsapp');
    expect(par('wf-erreur-form').textContent).toBe('Coche la case liée à la réservation pour continuer.');
    expect(appels('/join')).toHaveLength(0);
  });

  test('K — double clic : UN partage, UNE réservation', async () => {
    routeur();
    const fen = fenetre();
    window.open = jest.fn(() => fen);
    await jusquAuPartage();
    await coordonnees();
    await act(async () => { par('wf-inviter-whatsapp').click(); par('wf-inviter-whatsapp').click(); par('wf-inviter-whatsapp').click(); });
    await vider();
    expect(window.open).toHaveBeenCalledTimes(1);
    expect(appels('/chain/share')).toHaveLength(0);          // V618k : partage écrit par le join
    expect(appels('/join')).toHaveLength(1);
    expect(appels('/join')[0][1].partage_canal).toBe('whatsapp');
    expect(par('wf-essai-confirme')).not.toBeNull();
  });

  test('L — fenêtre WhatsApp refusée : place réservée quand même + Ouvrir WhatsApp / Copier mon lien / Partager autrement', async () => {
    routeur();
    window.open = jest.fn(() => null);
    await jusquAuPartage();
    await coordonnees();
    await cliquer('wf-inviter-whatsapp');
    expect(appels('/join')).toHaveLength(1);
    expect(par('wf-essai-confirme').textContent).toContain('Ta place est réservée');
    expect(par('wf-whatsapp-bloque').textContent).toContain('Tu peux copier ton lien pour inviter ton ami.');
    expect(decodeURIComponent(par('wf-ouvrir-whatsapp').getAttribute('href'))).toContain('https://afroboost.com/api/share/duo/T1');
    expect(par('wf-copier-lien')).not.toBeNull();
    expect(par('wf-partager-lien')).not.toBeNull();
    expect(evenementsSuivis()).not.toContain('partage_whatsapp_declenche');   // rien n'a été ouvert
  });

  test('refus du serveur au join : fenêtre refermée, message clair, on reste sur « Essai prêt »', async () => {
    routeur({ join: () => Promise.reject({ response: { status: 409, headers: { 'x-refus-raison': 'invitation_requise' }, data: {} } }) });
    const fen = await confirmerPlace();
    expect(fen.close).toHaveBeenCalled();
    expect(fen.location.href).toBe('');
    expect(par('wf-essai-pret')).not.toBeNull();
    expect(par('wf-erreur-form').textContent).toBe("Invite d'abord un ami pour débloquer ton essai gratuit.");
    expect(evenementsSuivis()).not.toContain('partage_whatsapp_declenche');
  });

  test('V618j — déjà client / essai déjà pris : place non confirmée, encart doux + « Accéder à mon espace membre », plus de bouton vert', async () => {
    routeur({ join: () => Promise.reject({ response: { status: 409, headers: { 'x-refus-raison': 'free_trial_already_used' }, data: {} } }) });
    const fen = await confirmerPlace();
    expect(fen.close).toHaveBeenCalled();
    expect(par('wf-essai-confirme')).toBeNull();
    expect(par('wf-erreur-form')).toBeNull();                       // plus de long message rouge
    expect(par('wf-refus-membre')).not.toBeNull();
    expect(par('bouton-espace-membre').textContent).toMatch(/espace membre/i);
    expect(par('wf-inviter-whatsapp')).toBeNull();                  // l'action ne se présente plus comme réussissable
  });

  test('V618j — refus NEUTRE « not_eligible » (membre actif) : même encart, aucune révélation de l’adresse', async () => {
    routeur({ join: () => Promise.reject({ response: { status: 409, headers: { 'x-refus-raison': 'not_eligible' }, data: {} } }) });
    await confirmerPlace();
    // V618k : uniquement le titre (en question : aucune révélation) + le bouton.
    expect(par('wf-refus-membre-titre').textContent).toMatch(/Tu es déjà membre Afroboost \?/);
    expect(par('bouton-espace-membre')).not.toBeNull();
    expect(par('wf-inviter-whatsapp')).toBeNull();
    expect(par('wf-retour')).toBeNull();                               // plus de « Changer ma séance »
    expect(appels('/chain/share')).toHaveLength(0);                    // aucun faux partage
    expect(evenementsSuivis()).not.toContain('partage_whatsapp_declenche');
  });

  test('V618k — après un refus, corriger son e-mail prépare une NOUVELLE invitation de l’ami (l’ancienne est libérée)', async () => {
    let refus = true;
    routeur({ join: () => (refus
      ? Promise.reject({ response: { status: 409, headers: { 'x-refus-raison': 'not_eligible' }, data: {} } })
      : Promise.resolve({ data: { status: 'unlocked', tickets: [] } })) });
    await confirmerPlace();
    const avant = appels('/chain').length;
    refus = false;
    await saisir('wf-email', 'autre@example.com');
    await vider();
    expect(par('wf-refus-membre')).toBeNull();
    expect(appels('/chain').length).toBe(avant + 1);                  // nouvelle création
    expect(par('wf-inviter-whatsapp')).not.toBeNull();
  });

  test('« Partager autrement » : partage natif ABOUTI → partage « share » enregistré + place confirmée ; annulé → rien', async () => {
    routeur();
    navigator.share = jest.fn(() => Promise.reject(Object.assign(new Error('x'), { name: 'AbortError' })));
    try {
      await jusquAuPartage();
      await coordonnees();
      await cliquer('wf-partager-autrement');
      expect(appels('/chain/share')).toHaveLength(0);
      expect(appels('/join')).toHaveLength(0);
      expect(par('wf-essai-pret')).not.toBeNull();
      navigator.share = jest.fn(() => Promise.resolve());
      await cliquer('wf-partager-autrement');
      expect(appels('/chain/share')).toHaveLength(0);                    // V618k : écrit par le join
      expect(appels('/join')).toHaveLength(1);
      expect(appels('/join')[0][1].partage_canal).toBe('share');
      expect(par('wf-essai-confirme')).not.toBeNull();
      expect(evenementsSuivis()).toContain('partage_autre_declenche');
    } finally { delete navigator.share; }
  });

  test('I/J — retour après WhatsApp / rechargement sur CET appareil : « Ta place est réservée » directement', async () => {
    window.localStorage.setItem(cleChaine('T0'), 'K1');
    const confirmePub = Object.assign({}, PUB, { status: 'unlocked', chain_required: false, chain: { exists: true, shared: true } });
    axios.get.mockImplementation((url) => (String(url).endsWith('/chain/options')
      ? Promise.resolve({ data: OPTS }) : Promise.resolve({ data: confirmePub })));
    await monter(<InvitationDuo token="T0" />);
    expect(par('wf-essai-confirme')).not.toBeNull();
    expect(par('wf-essai-confirme').textContent).toContain('Ta place est réservée');
    expect(par('wf-essai-confirme-seance').textContent).toContain('Valangines, Neuchâtel');
    expect(par('wf-inviter-encore').textContent).toContain('Inviter un autre ami');
    expect(par('wf-essai-accueil')).toBeNull();
    expect(par('wf-nom')).toBeNull();
    expect(par('invitation-form')).toBeNull();
    expect(conteneur.textContent).not.toContain('Finaliser');
    expect(conteneur.textContent).not.toContain('déjà utilisé cette invitation');
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('V618j — autre appareil (sans clé) sur un essai confirmé : « Ta place est déjà réservée », aucun formulaire, rien de personnel', async () => {
    const confirmePub = Object.assign({}, PUB, { status: 'unlocked', chain_required: false, chain: { exists: true, shared: true } });
    axios.get.mockImplementation((url) => (String(url).endsWith('/chain/options')
      ? Promise.resolve({ data: OPTS }) : Promise.resolve({ data: confirmePub })));
    await monter(<InvitationDuo token="T0" />);
    expect(par('wf-essai-confirme')).toBeNull();
    expect(par('invitation-deja-rejoint')).toBeNull();
    expect(par('essai-deja-reserve')).not.toBeNull();
    expect(par('essai-deja-reserve').textContent).toMatch(/déjà réservée/);
    expect(par('essai-voir-reservation')).not.toBeNull();
    expect(par('essai-partager-invitation')).not.toBeNull();
    expect(par('wf-email')).toBeNull();
    expect(document.body.textContent).not.toMatch(/@/);
  });

  test('V607g — « Inviter un autre ami » : un NOUVEAU lien par ami (jamais le lien déjà utilisé), un seul appel par clic', async () => {
    routeur();
    const fen = await confirmerPlace('Sophie');
    fen.location.href = '';
    // double clic : un seul POST /chain/next
    await act(async () => { par('wf-inviter-encore').click(); par('wf-inviter-encore').click(); });
    await vider();
    const suivantes = () => appels('/chain/next');
    expect(suivantes()).toHaveLength(1);
    expect(suivantes()[0][2].headers).toEqual({ 'X-Chain-Key': 'K1' });
    expect(decodeURIComponent(fen.location.href)).toContain('https://afroboost.com/api/share/duo/T2?v=0');
    expect(decodeURIComponent(fen.location.href)).not.toContain('/duo/T1');
    const partage = appels('/chain/share').pop();
    expect(partage[1]).toEqual({ channel: 'whatsapp', child_token: 'T2' });
    expect(par('wf-encore-compte').textContent).toBe('1 nouvelle invitation partagée');
    fen.location.href = '';
    await cliquer('wf-inviter-encore');
    expect(suivantes()).toHaveLength(2);
    expect(decodeURIComponent(fen.location.href)).toContain('/duo/T3?v=0');
    expect(par('wf-encore-compte').textContent).toBe('2 nouvelles invitations partagées');
    expect(appels('/join')).toHaveLength(1);                       // jamais une 2e réservation
    expect(conteneur.textContent).not.toMatch(/envoy[ée]/i);
  });

  test('V607g — plafond serveur : message clair, rien n’est ouvert', async () => {
    routeur();
    await confirmerPlace('Sophie');
    const base = axios.post.getMockImplementation();
    axios.post.mockImplementation((url, ...rest) => (String(url).endsWith('/chain/next')
      ? Promise.reject({ response: { status: 409, headers: { 'x-refus-raison': 'invitations_ouvertes_max' }, data: {} } })
      : base(url, ...rest)));
    const fen = fenetre();
    window.open = jest.fn(() => fen);
    await cliquer('wf-inviter-encore');
    expect(fen.close).toHaveBeenCalled();
    expect(par('wf-info').textContent).toContain('attends qu’un ami s’inscrive');
  });

  test('séance refusée par le serveur → message clair, on reste sur l’accueil (aucune bascule silencieuse)', async () => {
    routeur();
    axios.patch.mockImplementation(() => Promise.reject({ response: { status: 400, headers: { 'x-refus-raison': 'seance_indisponible' }, data: {} } }));
    await monter(<InvitationDuo token="T0" />);
    await choisirDimanche();                // V610k : le choix vaut validation
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

describe('V610k — le mot audio de l\'invitation sur « Ton essai est prêt »', () => {
  let play; let pause;
  beforeEach(() => {
    pause = jest.spyOn(window.HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  });
  afterEach(() => { if (play) play.mockRestore(); pause.mockRestore(); play = null; });

  test('audio configuré : lecteur monté caché dès l\'accueil, lancé PENDANT le clic « Valider ma séance », une seule fois, jamais en boucle', async () => {
    let appelsAuClic = null;
    play = jest.spyOn(window.HTMLMediaElement.prototype, 'play').mockImplementation(() => Promise.resolve());
    routeur({ audio: '/api/files/a1/mot.mp3' });
    await monter(<InvitationDuo token="T0" />);
    const bloc = par('wf-audio-essai');
    expect(bloc).not.toBeNull();
    expect(bloc.style.display).toBe('none');                     // caché sur l'accueil
    expect(play).not.toHaveBeenCalled();                          // rien sans geste
    await act(async () => { par('wf-valider-seance').click(); appelsAuClic = play.mock.calls.length; });
    await vider();
    expect(appelsAuClic).toBe(1);                                 // lancé DANS le geste (Safari)
    expect(par('wf-essai-pret')).not.toBeNull();
    expect(par('wf-audio-essai')).toBe(bloc);                     // MÊME élément : la lecture continue
    expect(par('wf-audio-essai').style.display).toBe('block');
    const audio = par('wf-audio-essai-audio');
    expect(audio.getAttribute('src')).toBe('/api/files/a1/mot.mp3');
    expect(audio.loop).toBe(false);
    expect(play).toHaveBeenCalledTimes(1);                        // une seule tentative
    expect(par('wf-afroboosteur').textContent).toContain('Deviens Afroboosteur');
    // ordre : titre, séance, « Deviens Afroboosteur », lecteur, consigne
    const ordre = [...par('wf-essai-pret').querySelectorAll('[data-testid]')].map((e) => e.dataset.testid);
    expect(ordre.indexOf('wf-rappel-seance')).toBeLessThan(ordre.indexOf('wf-afroboosteur'));
    expect(ordre.indexOf('wf-afroboosteur')).toBeLessThan(ordre.indexOf('wf-audio-essai'));
    expect(ordre.indexOf('wf-audio-essai')).toBeLessThan(ordre.indexOf('wf-essai-pret-texte'));
  });

  test('navigateur qui refuse : parcours intact, lecteur visible « Écouter le message » (fallback)', async () => {
    play = jest.spyOn(window.HTMLMediaElement.prototype, 'play').mockImplementation(() => Promise.reject(new Error('NotAllowedError')));
    routeur({ audio: '/api/files/a1/mot.mp3' });
    await monter(<InvitationDuo token="T0" />);
    await cliquer('wf-valider-seance');
    expect(par('wf-essai-pret')).not.toBeNull();
    expect(par('wf-audio-essai-bouton').textContent).toMatch(/Écouter le message/);
    expect(par('wf-inviter-whatsapp')).not.toBeNull();
  });

  test('aucun audio configuré : rien n\'est affiché ni inventé', async () => {
    play = jest.spyOn(window.HTMLMediaElement.prototype, 'play').mockImplementation(() => Promise.resolve());
    routeur();
    await monter(<InvitationDuo token="T0" />);
    await cliquer('wf-valider-seance');
    expect(par('wf-essai-pret')).not.toBeNull();
    expect(par('wf-audio-essai')).toBeNull();
    expect(par('wf-afroboosteur')).toBeNull();
    expect(play).not.toHaveBeenCalled();
  });
});

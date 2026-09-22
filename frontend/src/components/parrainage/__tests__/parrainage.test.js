/**
 * V534 — CENTRE PARRAINAGE / PASS DUO : le banc du front.
 *
 * CE QU'IL PROUVE
 *   1. `parrainageActifCache()` répond SANS réseau (jamais axios), et « non »
 *      sans cache, avec un cache fermé, ou avec un cache périmé ;
 *   2. `enteteParrain()` choisit le bon en-tête selon la session : jeton
 *      d'espace d'abord, jeton d'appareil sinon, rien sans identité — jamais
 *      X-User-Email ;
 *   3. PassDuoCard rend les SEPT états d'un pass avec le bon chip, le bon
 *      stepper, le texte EXACT « sponsor_sans_seance », les billets quand c'est
 *      débloqué, l'annulation confirmée EN LIGNE (jamais window.confirm) ;
 *   4. la mini-carte du ChatWidget est gardée par `parrainageActifCache()` —
 *      preuve de SOURCE (le montage de ChatWidget tire la moitié de l'app) —
 *      et cette garde vaut `false` quand le cache dit false ;
 *   5. la page /duo : consentement JAMAIS pré-coché, refus 409 traduits, 410/404.
 *
 * axios est mocké : aucun réseau. `beforeEach` réarme les mocks (CRA resetMocks).
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import fs from 'fs';
import path from 'path';
import PassDuoCard, { TEXTE_SPONSOR_SANS_SEANCE, optionsSeances } from '../PassDuoCard';
import InvitationDuo from '../InvitationDuo';
import CentreParrainage from '../CentreParrainage';
import CarteParrainage from '../CarteParrainage';
import { SectionParrainage, bornesPeriode, parametresParrainage } from '../../analytics/AnalyticsCockpit';
import {
  parrainageActifCache, enteteParrain, lireConfigParrainage, coursDuoEnCache, lienWhatsApp,
  messageRefus, etapePass, passCourant, libelleOccurrence, CLE_CACHE_PARRAINAGE, _resetParrainagePourTest,
} from '../../../utils/parrainage';

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), patch: jest.fn(), delete: jest.fn() },
}));
jest.mock('qrcode.react', () => ({
  QRCodeSVG: (p) => <svg data-testid="qr-svg" data-value={p.value} />,
  QRCodeCanvas: (p) => <canvas data-testid="qr-canvas" data-value={p.value} />,
}));
jest.mock('../../../utils/spordateHandoff', () => ({
  __esModule: true,
  prechargerSpordate: jest.fn(),
  entrerDansSpordate: jest.fn(),
}));

let conteneur, racine;
beforeEach(() => {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  jest.clearAllMocks();
  axios.get.mockReset(); axios.post.mockReset();
  window.localStorage.clear();
  _resetParrainagePourTest();
});
afterEach(() => {
  if (racine) act(() => racine.unmount());
  racine = null;
  conteneur.remove();
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const tous = (id) => conteneur.querySelectorAll(`[data-testid="${id}"]`);

async function monter(element) {
  await act(async () => {
    racine = createRoot(conteneur);
    racine.render(element);
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
}

const COURSE = { id: 'c1', name: 'Afroboost Dimanche', time: '18:30', locationName: 'Bord du Lac, Auvernier', mapsUrl: 'https://maps.google.com/?q=x' };
const OCC = '2026-09-27T18:30:00';
function pass(status, extra) {
  return Object.assign({
    id: `p-${status}`, status, status_label: status, course: COURSE, occurrence: OCC,
    share_token: 'TOK123', invite_url: 'https://afroboost.com/duo/TOK123',
    // V538 : le lien PARTAGÉ est la page d'aperçu, pas la page React.
    share_url: 'https://afroboost.com/api/share/duo/TOK123',
    whatsapp_text: 'Rejoins-moi https://afroboost.com/api/share/duo/TOK123', invitee: null, tickets: [],
    blocked_reason: null, created_at: '2026-09-18T10:00:00Z', unlocked_at: null, expires_at: OCC,
  }, extra || {});
}
const TICKETS = [
  { role: 'sponsor', first_name: 'Bassi', reservationCode: 'AF3B9C', qr_value: 'https://afroboost.com/validate/AF3B9C?res=1', validated: false },
  { role: 'invitee', first_name: 'Aminata', reservationCode: 'AF7D1A', qr_value: 'https://afroboost.com/validate/AF7D1A?res=2', validated: false },
];
const CONFIG = { enabled: true, courses: [{ ...COURSE, weekday: 0, date: '2026-09-27', occurrences: [OCC, '2026-10-04T18:30:00'] }] };
const poserCache = (enabled, ts) => window.localStorage.setItem(CLE_CACHE_PARRAINAGE, JSON.stringify({ enabled, courses: CONFIG.courses, ts: ts === undefined ? Date.now() : ts }));

// ═══ 1. Cache synchrone ═══════════════════════════════════════════════════════
describe('parrainageActifCache — synchrone, zéro réseau', () => {
  test('sans cache → false, et axios n\'est JAMAIS appelé', () => {
    expect(parrainageActifCache()).toBe(false);
    expect(axios.get).not.toHaveBeenCalled();
  });
  test('cache fermé → false ; cache ouvert et frais → true ; cache périmé → false', () => {
    poserCache(false); expect(parrainageActifCache()).toBe(false);
    poserCache(true); expect(parrainageActifCache()).toBe(true);
    poserCache(true, Date.now() - 11 * 60 * 1000); expect(parrainageActifCache()).toBe(false);
    expect(axios.get).not.toHaveBeenCalled();
  });
  test('coursDuoEnCache lit la liste des cours éligibles', () => {
    poserCache(true);
    expect(coursDuoEnCache('c1')).toBe(true);
    expect(coursDuoEnCache('autre')).toBe(false);
    expect(coursDuoEnCache('')).toBe(false);
  });
  test('lireConfigParrainage : UN appel, puis le cache ; jamais d\'exception en cas d\'échec', async () => {
    axios.get.mockResolvedValue({ data: CONFIG });
    const a = await lireConfigParrainage();
    const b = await lireConfigParrainage();
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(a.enabled).toBe(true); expect(b.courses.length).toBe(1);
    expect(parrainageActifCache()).toBe(true);
    _resetParrainagePourTest();
    axios.get.mockRejectedValue(new Error('réseau'));
    const c = await lireConfigParrainage();
    expect(c).toEqual({ enabled: false, courses: [] });
  });
});

// ═══ 2. En-tête du parrain ════════════════════════════════════════════════════
describe('enteteParrain — selon la session', () => {
  test('sans identité → {} (le serveur répondra 403)', () => {
    expect(enteteParrain()).toEqual({});
  });
  test('jeton d\'appareil seul → X-Subscriber-Token', () => {
    window.localStorage.setItem('afroboost_subscriber_token', 'dev-1');
    expect(enteteParrain()).toEqual({ 'X-Subscriber-Token': 'dev-1' });
  });
  test('jeton d\'espace vivant → x-espace-token, prioritaire sur l\'appareil', () => {
    window.localStorage.setItem('afroboost_subscriber_token', 'dev-1');
    window.localStorage.setItem('afroboost_espace_token', JSON.stringify({ token: 'esp-1', code: 'AFR-1', expires_at: new Date(Date.now() + 3600000).toISOString() }));
    expect(enteteParrain()).toEqual({ 'x-espace-token': 'esp-1' });
  });
  test('jeton d\'espace PÉRIMÉ → on retombe sur l\'appareil ; jamais X-User-Email', () => {
    window.localStorage.setItem('afroboost_subscriber_token', 'dev-1');
    window.localStorage.setItem('afroboost_espace_token', JSON.stringify({ token: 'esp-1', code: 'AFR-1', expires_at: new Date(Date.now() - 1000).toISOString() }));
    const h = enteteParrain();
    expect(h).toEqual({ 'X-Subscriber-Token': 'dev-1' });
    expect(Object.keys(h).map((k) => k.toLowerCase())).not.toContain('x-user-email');
  });
});

// ═══ 3. Les sept états du Pass Duo ═════════════════════════════════════════════
describe('PassDuoCard — les sept états', () => {
  const rendre = (p, extra) => monter(
    <PassDuoCard config={CONFIG} passes={[p]} passAffiche={p} initialeParrain="B" urlEspace="/espace/AFR-1"
                 onCreer={jest.fn()} onAnnuler={jest.fn()} onConfirmer={jest.fn()} onChoisir={jest.fn()} occupe={false} erreur="" {...(extra || {})} />
  );

  test('locked → chip Verrouillé, cadenas, stepper à 0, Annuler visible', async () => {
    await rendre(pass('locked'));
    expect(par('pass-duo-card').getAttribute('data-status')).toBe('locked');
    expect(par('chip-locked').textContent).toContain('Verrouillé');
    expect(par('pass-rond-lock')).not.toBeNull();
    expect(par('stepper').getAttribute('data-etape')).toBe('0');
    expect(par('pass-annuler')).not.toBeNull();
    expect(par('billets-duo')).toBeNull();
  });
  test('waiting → « En attente de ton ami », stepper à 1', async () => {
    await rendre(pass('waiting'));
    expect(par('chip-waiting').textContent).toContain('En attente de ton ami');
    expect(par('stepper').getAttribute('data-etape')).toBe('1');
    expect(par('pass-texte-waiting')).not.toBeNull();
  });
  test('friend_registered + sponsor_sans_seance → texte EXACT + Réserver/Recharger + Confirmer ma place', async () => {
    const onConfirmer = jest.fn();
    await rendre(pass('friend_registered', { blocked_reason: 'sponsor_sans_seance', invitee: { first_name: 'Aminata' } }), { onConfirmer });
    expect(par('chip-friend_registered').textContent).toContain('Ami inscrit');
    expect(par('stepper').getAttribute('data-etape')).toBe('2');
    expect(par('pass-bloque-sans-seance').textContent).toBe(TEXTE_SPONSOR_SANS_SEANCE);
    expect(TEXTE_SPONSOR_SANS_SEANCE).toBe('Ton Pass Duo est prêt, mais tu dois disposer d’une séance pour confirmer ta place.');
    expect(par('pass-reserver-recharger').getAttribute('href')).toBe('/espace/AFR-1');
    await act(async () => { par('pass-confirmer').click(); });
    expect(onConfirmer).toHaveBeenCalledWith('p-friend_registered');
    expect(par('duo').textContent).toContain('Aminata');
  });
  test('unlocked → check, stepper à 3, DEUX billets avec QR du serveur, plus de bouton Annuler', async () => {
    await rendre(pass('unlocked', { tickets: TICKETS, invitee: { first_name: 'Aminata' } }));
    expect(par('chip-unlocked').textContent).toContain('Débloqué');
    expect(par('pass-rond-ok')).not.toBeNull();
    expect(par('stepper').getAttribute('data-etape')).toBe('3');
    expect(tous('qr-svg').length).toBe(2);
    expect(par('billet-sponsor').textContent).toContain('Séance déduite de ton forfait');
    expect(par('billet-invitee').textContent).toContain('Essai gratuit Afroboost');
    expect(tous('qr-svg')[0].getAttribute('data-value')).toBe(TICKETS[0].qr_value);
    expect(par('pass-annuler')).toBeNull();
  });
  test('used → « Participation validée », billets marqués validés', async () => {
    await rendre(pass('used', { tickets: TICKETS.map((t) => ({ ...t, validated: true })) }));
    expect(par('chip-used').textContent).toContain('Participation validée');
    expect(par('billet-sponsor').className).toContain('cp-ticket--validated');
    expect(par('billet-sponsor').textContent).toContain('Participation validée');
  });
  test('expired → « Expiré », aucune action sauf « nouveau Pass »', async () => {
    await rendre(pass('expired'));
    expect(par('chip-expired').textContent).toContain('Expiré');
    expect(par('pass-annuler')).toBeNull();
    expect(par('pass-confirmer')).toBeNull();
    expect(par('pass-nouveau')).not.toBeNull();
    expect(par('stepper').querySelectorAll('span.on').length).toBe(0);
  });
  test('cancelled → « Annulé »', async () => {
    await rendre(pass('cancelled'));
    expect(par('chip-cancelled').textContent).toContain('Annulé');
    expect(par('pass-texte-ferme').textContent).toContain('annulé');
  });
  test('annulation confirmée EN LIGNE — jamais window.confirm', async () => {
    const onAnnuler = jest.fn();
    const confirmSpy = jest.spyOn(window, 'confirm').mockImplementation(() => true);
    await rendre(pass('waiting'), { onAnnuler });
    await act(async () => { par('pass-annuler').click(); });
    expect(par('pass-annuler-confirm')).not.toBeNull();
    expect(onAnnuler).not.toHaveBeenCalled();
    await act(async () => { par('pass-annuler-oui').click(); });
    expect(onAnnuler).toHaveBeenCalledWith('p-waiting');
    expect(confirmSpy).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
  test('sans pass → sélecteur de séance (libellé calculé) + « Créer mon Pass Duo »', async () => {
    const onCreer = jest.fn();
    // V534: ConditionsParticipation interroge /terms/active — ici aucune condition publiée
    axios.get.mockResolvedValue({ data: { required: false } });
    await monter(<PassDuoCard config={CONFIG} passes={[]} passAffiche={null} onCreer={onCreer} onAnnuler={jest.fn()} onConfirmer={jest.fn()} onChoisir={jest.fn()} occupe={false} erreur="" />);
    const sel = par('pass-select-seance');
    expect(sel.options.length).toBe(2);
    expect(sel.options[0].textContent).toMatch(/^Dimanche 27 sept\. · 18:30 — Bord du Lac, Auvernier$/);
    await act(async () => { par('pass-creer').click(); });
    expect(onCreer).toHaveBeenCalledWith('c1', OCC, false, null); // V534b: offer_id null = config sans catalogue
  });
  test('V534 conditions publiées → la création exige la case cochée, puis transmet terms_accepted=true', async () => {
    const onCreer = jest.fn();
    axios.get.mockResolvedValue({ data: { required: true, version: 'v1', text: 'Conditions de test' } });
    await monter(<PassDuoCard config={CONFIG} passes={[]} passAffiche={null} onCreer={onCreer} onAnnuler={jest.fn()} onConfirmer={jest.fn()} onChoisir={jest.fn()} occupe={false} erreur="" />);
    expect(par('pass-conditions')).not.toBeNull();
    expect(par('pass-creer').disabled).toBe(true);
    const cases = par('pass-conditions').querySelectorAll('input[type="checkbox"]');
    expect(cases.length).toBeGreaterThan(0);
    await act(async () => { cases[0].click(); });
    expect(par('pass-creer').disabled).toBe(false);
    await act(async () => { par('pass-creer').click(); });
    expect(onCreer).toHaveBeenCalledWith('c1', OCC, true, null); // V534b
  });
  test('etapePass / passCourant / optionsSeances / libelleOccurrence', () => {
    expect([etapePass('locked'), etapePass('waiting'), etapePass('friend_registered'), etapePass('unlocked'), etapePass('used')]).toEqual([0, 1, 2, 3, 3]);
    expect(passCourant([pass('cancelled'), pass('waiting', { created_at: '2026-09-10' }), pass('locked', { created_at: '2026-09-19' })]).status).toBe('locked');
    expect(passCourant([pass('expired')])).toBeNull();
    expect(optionsSeances(CONFIG.courses)[0].options.length).toBe(2);
    expect(libelleOccurrence(OCC, 'Auvernier')).toBe('Dimanche 27 sept. · 18:30 — Auvernier');
  });
});

// ═══ 4. Centre : états de page + journal des invitations ═════════════════════
describe('CentreParrainage — états de page', () => {
  test('sans identité → « Ouvre ton espace abonné », AUCUN appel /me', async () => {
    await monter(<CentreParrainage />);
    expect(par('centre-non-connecte')).not.toBeNull();
    expect(axios.get).not.toHaveBeenCalled();
  });
  test('403 → non connecté avec lien vers l\'espace de la session', async () => {
    window.localStorage.setItem('afroboost_espace_token', JSON.stringify({ token: 'esp-1', code: 'AFR-1', expires_at: new Date(Date.now() + 3600000).toISOString() }));
    axios.get.mockImplementation((url) => (String(url).endsWith('/me') ? Promise.reject({ response: { status: 403 } }) : Promise.resolve({ data: CONFIG })));
    await monter(<CentreParrainage />);
    expect(par('centre-vers-espace').getAttribute('href')).toBe('/espace/AFR-1');
  });
  test('enabled:false → « Bientôt disponible »', async () => {
    window.localStorage.setItem('afroboost_subscriber_token', 'dev-1');
    axios.get.mockImplementation((url) => (String(url).endsWith('/me') ? Promise.resolve({ data: { enabled: false } }) : Promise.resolve({ data: { enabled: false, courses: [] } })));
    await monter(<CentreParrainage />);
    expect(par('centre-desactive').textContent).toContain('Bientôt');
  });
  test('centre complet : /me UNE fois, en-tête du parrain, résultats, journal « copy » → waiting', async () => {
    window.localStorage.setItem('afroboost_subscriber_token', 'dev-1');
    const ME = { enabled: true, sponsor: { first_name: 'Bassi', code: 'AFR-1' }, stats: { invited: 3, opened: 2, joined: 1, unlocked: 1, used: 0 },
      passes: [pass('locked')], invitations: [], history: [{ at: '2026-09-18T10:00:00Z', type: 'pass_created', label: 'Pass Duo créé.' }] };
    axios.get.mockImplementation((url) => (String(url).endsWith('/me') ? Promise.resolve({ data: ME }) : Promise.resolve({ data: CONFIG })));
    axios.post.mockResolvedValue({ data: { id: 'inv-1' } });
    Object.assign(navigator, { clipboard: { writeText: jest.fn().mockResolvedValue() } });
    await monter(<CentreParrainage />);
    expect(axios.get.mock.calls.filter((c) => String(c[0]).endsWith('/me')).length).toBe(1);
    expect(axios.get.mock.calls.find((c) => String(c[0]).endsWith('/me'))[1].headers).toEqual({ 'X-Subscriber-Token': 'dev-1' });
    expect(par('stat-invited').textContent).toContain('3');
    expect(par('stat-joined').textContent).toContain('1');
    expect(par('inviter-un-ami').textContent).toContain('afroboost.com/api/share/duo/TOK123');
    expect(par('historique').textContent).toContain('Pass Duo créé.');
    expect(par('programme-credits').textContent).toContain('1 crédit Sport Date par achat de ton filleul · jusqu\'à 50 filleuls');
    await act(async () => { par('inviter-copier').click(); });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/referral\/invitations$/), { pass_id: 'p-locked', channel: 'copy' }, expect.anything());
    expect(par('chip-waiting')).not.toBeNull();            // état local mis à jour, sans relancer /me
    expect(par('stat-invited').textContent).toContain('4');
    expect(axios.get.mock.calls.filter((c) => String(c[0]).endsWith('/me')).length).toBe(1);
  });
  test('sans pass → les quatre boutons sont désactivés avec explication', async () => {
    window.localStorage.setItem('afroboost_subscriber_token', 'dev-1');
    const ME = { enabled: true, sponsor: { first_name: 'Bassi' }, stats: {}, passes: [], invitations: [], history: [] };
    axios.get.mockImplementation((url) => (String(url).endsWith('/me') ? Promise.resolve({ data: ME }) : Promise.resolve({ data: CONFIG })));
    await monter(<CentreParrainage />);
    ['inviter-whatsapp', 'inviter-copier', 'inviter-qr', 'inviter-partager'].forEach((id) => expect(par(id).disabled).toBe(true));
    expect(par('inviter-un-ami').textContent).toContain('Crée ton Pass Duo');
    expect(par('pass-select-seance')).not.toBeNull();
  });

  // ═══ V538 : les deux états du parcours, et le lien réellement partagé ═════
  test('CAS A — sans Pass : le CTA « Créer mon Pass Duo » domine, avant les boutons de partage', async () => {
    window.localStorage.setItem('afroboost_subscriber_token', 'dev-1');
    const ME = { enabled: true, sponsor: { first_name: 'Bassi' }, stats: {}, passes: [], invitations: [], history: [] };
    axios.get.mockImplementation((url) => (String(url).endsWith('/me') ? Promise.resolve({ data: ME }) : Promise.resolve({ data: CONFIG })));
    await monter(<CentreParrainage />);
    expect(par('creer-pass-cta')).not.toBeNull();
    expect(par('creer-pass-bouton').textContent).toContain('Créer mon Pass Duo');
    const html = document.body.innerHTML;
    expect(html.indexOf('creer-pass-cta')).toBeLessThan(html.indexOf('inviter-un-ami'));
  });
  test('CAS B — Pass créé : le CTA disparaît, « Inviter un ami » devient l\'action', async () => {
    window.localStorage.setItem('afroboost_subscriber_token', 'dev-1');
    const ME = { enabled: true, sponsor: { first_name: 'Bassi' }, stats: {}, passes: [pass('locked')], invitations: [], history: [] };
    axios.get.mockImplementation((url) => (String(url).endsWith('/me') ? Promise.resolve({ data: ME }) : Promise.resolve({ data: CONFIG })));
    await monter(<CentreParrainage />);
    expect(par('creer-pass-cta')).toBeNull();
    ['inviter-whatsapp', 'inviter-copier', 'inviter-qr', 'inviter-partager'].forEach((id) => expect(par(id).disabled).toBe(false));
  });
  test('CAS C/J/K/L — WhatsApp, Copier, QR et Partager utilisent TOUS le lien d\'aperçu', async () => {
    window.localStorage.setItem('afroboost_subscriber_token', 'dev-1');
    const ME = { enabled: true, sponsor: { first_name: 'Bassi' }, stats: {}, passes: [pass('locked')], invitations: [], history: [] };
    axios.get.mockImplementation((url) => (String(url).endsWith('/me') ? Promise.resolve({ data: ME }) : Promise.resolve({ data: CONFIG })));
    axios.post.mockResolvedValue({ data: { id: 'inv-1' } });
    const ecrire = jest.fn().mockResolvedValue();
    Object.assign(navigator, { clipboard: { writeText: ecrire } });
    const ouvrir = jest.spyOn(window, 'open').mockImplementation(() => null);
    await monter(<CentreParrainage />);
    expect(par('inviter-un-ami').textContent).toContain('afroboost.com/api/share/duo/TOK123');
    await act(async () => { par('inviter-whatsapp').click(); });
    expect(String(ouvrir.mock.calls[0][0])).toContain(encodeURIComponent('https://afroboost.com/api/share/duo/TOK123'));
    await act(async () => { par('inviter-copier').click(); });
    await act(async () => { await Promise.resolve(); });
    expect(ecrire).toHaveBeenCalledWith('https://afroboost.com/api/share/duo/TOK123');
    await act(async () => { par('inviter-qr').click(); });
    expect(document.body.innerHTML).toContain('share/duo/TOK123');   // le QR porte le même lien
    ouvrir.mockRestore();
  });
  test('CAS N/O — annulation : les compteurs sont RELUS côté serveur, l\'historique reste', async () => {
    window.localStorage.setItem('afroboost_subscriber_token', 'dev-1');
    const AVANT = { enabled: true, sponsor: { first_name: 'Bassi' }, stats: { invited: 2, joined: 1, unlocked: 0 },
      passes: [pass('waiting')], invitations: [{ id: 'i1', pass_id: 'p-waiting', channel: 'whatsapp', created_at: OCC }],
      history: [{ at: OCC, type: 'pass_created', label: 'Pass Duo créé.' }] };
    const APRES = Object.assign({}, AVANT, { stats: { invited: 0, joined: 0, unlocked: 0 }, passes: [pass('cancelled')] });
    let appels = 0;
    axios.get.mockImplementation((url) => {
      if (!String(url).endsWith('/me')) return Promise.resolve({ data: CONFIG });
      appels += 1;
      return Promise.resolve({ data: appels === 1 ? AVANT : APRES });
    });
    axios.post.mockResolvedValue({ data: pass('cancelled') });
    await monter(<CentreParrainage />);
    expect(par('stat-invited').textContent).toContain('2');
    await act(async () => { par('pass-annuler').click(); });        // ouvre la confirmation
    await act(async () => { par('pass-annuler-oui').click(); });     // confirme
    await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
    expect(appels).toBeGreaterThan(1);                       // `/me` relu après l'annulation
    expect(par('stat-invited').textContent).toContain('0');  // les compteurs reviennent
    expect(par('historique').textContent).toContain('Pass Duo créé.');   // l'historique reste
  });
});

// ═══ 5. Page publique /duo ═══════════════════════════════════════════════════
describe('InvitationDuo — page publique', () => {
  const PUB = { status: 'waiting', sponsor_first_name: 'Bassi', course: COURSE, occurrence: OCC, expired: false };
  test('invitation : prénom, vrai cours, itinéraire, consentements NON pré-cochés', async () => {
    axios.get.mockResolvedValue({ data: PUB });
    await monter(<InvitationDuo token="TOK123" />);
    expect(par('invitation-de').textContent).toContain('Invitation de Bassi');
    expect(par('invitation-seance').textContent).toContain('Afroboost Dimanche');
    expect(par('invitation-seance').textContent).toContain('Dimanche 27 sept. · 18:30');
    expect(par('invitation-itineraire').getAttribute('href')).toBe(COURSE.mapsUrl);
    expect(par('invitation-consent').checked).toBe(false);
    expect(par('invitation-marketing').checked).toBe(false);
  });
  test('409 X-Refus-Raison → messages FR précis ; 410 ; 404', async () => {
    expect(messageRefus('free_trial_already_used')).toBe('Tu as déjà profité de l\'essai gratuit Afroboost');
    expect(messageRefus('free_trial_already_granted')).toBe('Tu as déjà profité de l\'essai gratuit Afroboost');
    expect(messageRefus('abonne_actif')).toBe('Tu es déjà membre : réserve directement depuis ton espace');
    expect(messageRefus('auto_parrainage')).toContain('ton lien');
    expect(messageRefus('deja_filleul_occurrence')).toContain('déjà inscrit');
    expect(messageRefus('pass_ferme')).toContain('plus ouvert');
    axios.get.mockRejectedValue({ response: { status: 410 } });
    await monter(<InvitationDuo token="X" />);
    expect(par('invitation-message').textContent).toContain('Cette invitation a expiré');
    act(() => racine.unmount()); racine = null;
    axios.get.mockRejectedValue({ response: { status: 404, data: { detail: 'introuvable' } } });
    await monter(<InvitationDuo token="Y" />);
    expect(par('invitation-message').textContent).toContain('Invitation introuvable');
    act(() => racine.unmount()); racine = null;
    axios.get.mockRejectedValue({ response: { status: 404, data: { detail: 'parrainage_duo_desactive' } } });
    await monter(<InvitationDuo token="Z" />);
    expect(par('invitation-message').textContent).toContain('Invitation indisponible');
  });
  test('join → 409 affiché dans le formulaire ; succès → « Pass Duo débloqué » + billets', async () => {
    axios.get.mockResolvedValue({ data: PUB });
    await monter(<InvitationDuo token="TOK123" />);
    const saisir = (id, v) => act(async () => {
      const el = par(id);
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await saisir('invitation-prenom', 'Aminata');
    await saisir('invitation-email', 'aminata@example.com');
    await saisir('invitation-whatsapp', '+41 79 000 00 00');
    await act(async () => { par('invitation-consent').click(); });
    axios.post.mockRejectedValueOnce({ response: { status: 409, headers: { 'x-refus-raison': 'abonne_actif' } } });
    await act(async () => { par('invitation-rejoindre').click(); });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(par('invitation-erreur').textContent).toBe('Tu es déjà membre : réserve directement depuis ton espace');
    const corps = axios.post.mock.calls[0][1];
    expect(corps).toMatchObject({ name: 'Aminata', email: 'aminata@example.com', consent_reservation: true, terms_accepted: true, marketing_consent: false });
    axios.post.mockResolvedValueOnce({ data: { status: 'unlocked', tickets: TICKETS, blocked_reason: null } });
    await act(async () => { par('invitation-rejoindre').click(); });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(par('invitation-succes').textContent).toContain('débloqué');
    expect(tous('qr-svg').length).toBe(2);
  });
  test('friend_registered → « Inscription confirmée », ton ami confirme sa place', async () => {
    axios.get.mockResolvedValue({ data: PUB });
    await monter(<InvitationDuo token="TOK123" />);
    const saisir = (id, v) => act(async () => {
      const el = par(id);
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(el, v);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await saisir('invitation-prenom', 'Léa'); await saisir('invitation-email', 'lea@example.com'); await saisir('invitation-whatsapp', '0790000000');
    await act(async () => { par('invitation-consent').click(); });
    axios.post.mockResolvedValueOnce({ data: { status: 'friend_registered', tickets: [TICKETS[1]], blocked_reason: 'sponsor_sans_seance' } });
    await act(async () => { par('invitation-rejoindre').click(); });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(par('invitation-succes-attente').textContent).toContain('Inscription confirmée');
    expect(par('invitation-succes-attente').textContent).toContain('Bassi confirme la sienne');
    expect(tous('qr-svg').length).toBe(1);
  });
});

// ═══ 6. Points d'entrée ═══════════════════════════════════════════════════════
describe('Points d\'entrée', () => {
  const SRC_CHAT = fs.readFileSync(path.join(__dirname, '..', '..', 'ChatWidget.js'), 'utf8');
  const debut = SRC_CHAT.indexOf("'data-testid': 'chat-parrainage-mini'");
  const garde = SRC_CHAT.slice(SRC_CHAT.lastIndexOf('{!isCoachMode', debut), debut);
  const bloc = SRC_CHAT.slice(debut, SRC_CHAT.indexOf('})()}', debut));

  test('mini-carte du chat : gardée par parrainageActifCache(), afroboostProfile.code et !isCoachMode', () => {
    expect(garde).toContain('parrainageActifCache()');
    expect(garde).toContain('afroboostProfile.code');
    expect(garde).toContain('!isCoachMode');
  });
  test('mini-carte masquée quand le cache dit false (la garde vaut false, sans réseau)', () => {
    poserCache(false);
    expect(parrainageActifCache()).toBe(false);
    expect(axios.get).not.toHaveBeenCalled();
  });
  test('mini-carte : ZÉRO réseau, ZÉRO minuteur périodique, ZÉRO état nouveau, style ES5', () => {
    expect(bloc).not.toMatch(/axios|fetch\(/);
    expect(bloc).not.toContain('setInterval');
    expect(bloc).not.toMatch(/useState|useEffect|setAfroboostProfile/);
    expect(bloc).not.toMatch(/=>/);
    expect(bloc).not.toMatch(/\bconst\b|\blet\b/);
    expect(bloc).toContain('React.createElement');
  });
  test('menu ⋮ : entrée « Parrainage » après « Mon profil », même garde', () => {
    const i = SRC_CHAT.indexOf("data-testid=\"open-parrainage\"");
    expect(i).toBeGreaterThan(SRC_CHAT.indexOf('data-testid="open-profile-form"'));
    expect(SRC_CHAT.slice(i - 900, i)).toContain('parrainageActifCache()');
  });
  test('CarteParrainage : rien si fermé ; deux boutons vers /parrainage si ouvert', async () => {
    await monter(<CarteParrainage enabled={false} />);
    expect(par('carte-parrainage')).toBeNull();
    act(() => racine.unmount()); racine = null;
    await monter(<CarteParrainage enabled />);
    expect(par('carte-parrainage').textContent).toContain('Invite un ami et viens à deux.');
    expect(par('carte-parrainage-inviter')).not.toBeNull();
    expect(par('carte-parrainage-voir')).not.toBeNull();
    expect(par('carte-parrainage').style.order).toBe('0');
  });
  test('lienWhatsApp encode le texte, sans ?ref=', () => {
    const l = lienWhatsApp('Rejoins-moi https://afroboost.com/duo/ABC');
    expect(l.startsWith('https://wa.me/?text=')).toBe(true);
    expect(decodeURIComponent(l.slice(20))).toBe('Rejoins-moi https://afroboost.com/duo/ABC');
    expect(l).not.toContain('ref=');
  });
});

// ═══ 7. Cockpit admin — bloc Parrainage ═══════════════════════════════════════
describe('AnalyticsCockpit — bloc Parrainage', () => {
  test('bornesPeriode : mêmes filtres que le cockpit, traduits en from/to', () => {
    const lundi = new Date(2026, 8, 21); // lundi 21 sept. 2026
    expect(bornesPeriode('aujourdhui', '', '', lundi)).toEqual({ from: '2026-09-21', to: '2026-09-21' });
    expect(bornesPeriode('semaine', '', '', new Date(2026, 8, 23))).toEqual({ from: '2026-09-21', to: '2026-09-23' });
    expect(bornesPeriode('mois', '', '', lundi)).toEqual({ from: '2026-09-01', to: '2026-09-21' });
    expect(bornesPeriode('annee', '', '', lundi)).toEqual({ from: '2026-01-01', to: '2026-09-21' });
    expect(bornesPeriode('perso', '2026-08-01', '2026-08-31')).toEqual({ from: '2026-08-01', to: '2026-08-31' });
    const p = parametresParrainage({ periode: 'perso', du: '2026-08-01', au: '2026-08-31', coachId: 'c@x', courseId: 'k', statut: 'unlocked' });
    expect(p).toEqual({ from: '2026-08-01', to: '2026-08-31', course_id: 'k', coach: 'c@x', status: 'unlocked' });
  });
  test('un appel par filtre, KPI affichés, changement de statut = un appel de plus, jamais de sondage', async () => {
    jest.useFakeTimers();
    axios.get.mockResolvedValue({ data: { kpi: { passes_crees: 12, invitations: 9, ouvertures: 7, inscriptions: 4, debloques: 3, utilises: 2, expires: 1, annules: 1, presences_duo: 2 }, par_canal: { whatsapp: 5, copy: 2, qr: 1, share: 1 } } });
    await monter(<SectionParrainage periode="mois" du="" au="" coachId="" courseId="c1" />);
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(axios.get.mock.calls[0][0]).toMatch(/\/referral\/admin\/summary$/);
    expect(axios.get.mock.calls[0][1].params.course_id).toBe('c1');
    expect(par('kpi-parrainage-passes').textContent).toContain('12');
    expect(par('kpi-parrainage-invitations').textContent).toContain('WhatsApp 5');
    expect(par('kpi-parrainage-presences').textContent).toContain('2');
    await act(async () => {
      const sel = par('parrainage-statut');
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(sel, 'unlocked');
      sel.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(axios.get).toHaveBeenCalledTimes(2);
    expect(axios.get.mock.calls[1][1].params.status).toBe('unlocked');
    act(() => { jest.advanceTimersByTime(10 * 60 * 1000); });
    expect(axios.get).toHaveBeenCalledTimes(2);
    jest.useRealTimers();
  });
  test('404 (drapeau OFF) → bloc masqué, aucune relance', async () => {
    axios.get.mockRejectedValue({ response: { status: 404 } });
    await monter(<SectionParrainage periode="mois" du="" au="" coachId="" courseId="" />);
    expect(par('section-parrainage')).toBeNull();
    expect(axios.get).toHaveBeenCalledTimes(1);
  });
});

/**
 * V552 — PAGE /parrainage COMPACTE : « Mes outils » + un tiroir commun.
 *
 * CE QU'IL PROUVE
 *   1. par défaut, la page ne rend plus le Pass Duo complet, ni la liste des
 *      invitations, ni l'historique, ni le bloc crédits : seulement les
 *      résultats, l'assistant d'invitation et QUATRE raccourcis ;
 *   2. chaque raccourci ouvre LE MÊME composant `ParrainageDrawer` (role
 *      dialog, aria-modal, titre) avec le contenu COMPLET d'avant ;
 *   3. fermer (bouton, Échap, fond) rend la page telle quelle : l'assistant
 *      n'a JAMAIS été démonté (même nœud DOM, texte saisi conservé) et le
 *      focus revient au raccourci ;
 *   4. ouvrir un tiroir ne déclenche AUCUN appel réseau (les données sont
 *      déjà chargées par l'unique GET /me du montage) ;
 *   5. Échap dans un sheet imbriqué (« Changer d'offre ») ne ferme QUE le sheet.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import CentreParrainage from '../CentreParrainage';
import ParrainageDrawer from '../ParrainageDrawer';
import { _resetParrainagePourTest } from '../../../utils/parrainage';

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
  axios.get.mockReset(); axios.post.mockReset(); axios.patch.mockReset();
  window.localStorage.clear();
  _resetParrainagePourTest();
});
afterEach(() => {
  if (racine) act(() => racine.unmount());
  racine = null;
  conteneur.remove();
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
async function monter(element) {
  await act(async () => { racine = createRoot(conteneur); racine.render(element); });
  await act(async () => { for (let i = 0; i < 10; i += 1) await Promise.resolve(); });
}
const touche = (key) => act(async () => { document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true })); });
const ecrire = (el, valeur) => {
  const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, valeur);
  el.dispatchEvent(new Event('input', { bubbles: true }));
};

const COURSE = { id: 'c1', name: 'Afroboost Dimanche', time: '18:30', locationName: 'Bord du Lac, Auvernier' };
const OCC = '2026-09-27T18:30:00';
const OFF_A = { id: 'off-a', name: 'Essai découverte', price: 0 };
const OFF_B = { id: 'off-b', name: 'Pack bienvenue', price: 0 };
const CONFIG = { enabled: true, courses: [{ ...COURSE, weekday: 0, date: '2026-09-27', occurrences: [OCC, '2026-10-04T18:30:00'], offers: [OFF_A, OFF_B] }] };
// Une seule offre : l'étape 1 de l'assistant est valide d'emblée (offre présélectionnée).
const CONFIG_1 = { enabled: true, courses: [{ ...COURSE, weekday: 0, date: '2026-09-27', occurrences: [OCC], offers: [OFF_A] }] };
function pass(status, extra) {
  return Object.assign({
    id: `p-${status}`, status, status_label: status, course: COURSE, occurrence: OCC,
    share_token: 'TOK', share_url: 'https://afroboost.com/api/share/duo/TOK', invite_url: 'https://afroboost.com/duo/TOK',
    whatsapp_text: 'Rejoins-moi', invitee: null, tickets: [], blocked_reason: null, offer: OFF_A, offers: [OFF_A, OFF_B], version: 3,
    created_at: '2026-09-18T10:00:00Z', expires_at: OCC,
  }, extra || {});
}
const ME_PASS = () => ({
  enabled: true, sponsor: { first_name: 'Bassi' }, stats: { invited: 2, joined: 1, unlocked: 0 },
  passes: [pass('waiting'), pass('expired', { id: 'p-old' })],
  invitations: [{ id: 'i1', pass_id: 'p-waiting', channel: 'whatsapp', created_at: OCC }, { id: 'i2', pass_id: 'p-old', channel: 'copy', created_at: OCC }],
  history: [{ at: OCC, type: 'pass_created', label: 'Pass Duo créé.' }],
});
const ME_VIDE = () => ({ enabled: true, sponsor: { first_name: 'Bassi' }, stats: {}, passes: [], invitations: [], history: [] });

async function monterCentre(me, config) {
  window.localStorage.setItem('afroboost_subscriber_token', 'dev-1');
  axios.get.mockImplementation((url) => {
    if (String(url).endsWith('/me')) return Promise.resolve({ data: me });
    if (String(url).indexOf('/terms/') >= 0) return Promise.resolve({ data: { required: false } });
    return Promise.resolve({ data: config || CONFIG });
  });
  await monter(<CentreParrainage />);
}
const ouvrir = (id) => act(async () => { par(`outil-${id}`).click(); });

describe('V552 — page compacte par défaut', () => {
  test('ni Pass Duo complet, ni liste des passes, ni invitations, ni historique, ni crédits ; 4 raccourcis', async () => {
    await monterCentre(ME_PASS());
    ['pass-duo-card', 'passes-liste', 'passes-item-p-old', 'mes-invitations', 'historique', 'programme-credits']
      .forEach((id) => expect(par(id)).toBeNull());
    expect(par('mes-resultats')).not.toBeNull();
    expect(par('invitation-zone')).not.toBeNull();
    const outils = par('mes-outils').querySelectorAll('button');
    expect(Array.from(outils).map((b) => b.getAttribute('data-testid')))
      .toEqual(['outil-credits', 'outil-pass', 'outil-invitations', 'outil-historique']);
    expect(par('outil-invitations').textContent).toContain('2');
    expect(par('outil-pass').textContent).toContain('En attente');
    expect(par('parrainage-drawer')).toBeNull();
    // L'assistant d'invitation vient AVANT les outils.
    const html = conteneur.innerHTML;
    expect(html.indexOf('invitation-zone')).toBeLessThan(html.indexOf('mes-outils'));
    // Aucune icône emoji dans les raccourcis : chaque bouton porte un SVG.
    Array.from(outils).forEach((b) => expect(b.querySelector('svg')).not.toBeNull());
  });

  test('mesure : nombre de sections rendues par défaut (h2 + blocs de premier niveau)', async () => {
    await monterCentre(ME_PASS());
    const app = conteneur.querySelector('.cp-app');
    expect(app.querySelectorAll('h2.cp-h2').length).toBe(2);           // Inviter un ami · Mes outils
    expect(app.querySelectorAll(':scope > .cp-card, :scope > [data-testid]').length).toBe(3); // résultats · invitation · outils
  });
});

describe('V552 — le tiroir commun', () => {
  test('chaque raccourci ouvre ParrainageDrawer avec le contenu complet, sans appel réseau', async () => {
    await monterCentre(ME_PASS());
    const getAvant = axios.get.mock.calls.length;
    const postAvant = axios.post.mock.calls.length;

    await ouvrir('pass');
    const tiroir = par('parrainage-drawer');
    expect(tiroir.getAttribute('role')).toBe('dialog');
    expect(tiroir.getAttribute('aria-modal')).toBe('true');
    expect(document.getElementById(tiroir.getAttribute('aria-labelledby')).textContent).toBe('Pass Duo');
    expect(par('pass-duo-card')).not.toBeNull();
    expect(par('pass-annuler')).not.toBeNull();            // annuler
    expect(par('pass-changer-seance')).not.toBeNull();     // changer de séance
    expect(par('passes-item-p-old')).not.toBeNull();       // les autres passes

    await ouvrir('invitations');
    expect(par('pass-duo-card')).toBeNull();               // un seul tiroir à la fois
    expect(par('mes-invitations').querySelectorAll('[data-testid="invitation-row"]').length).toBe(2);

    await ouvrir('historique');
    expect(par('historique').textContent).toContain('Pass Duo créé.');

    await ouvrir('credits');
    expect(par('programme-credits').textContent).toContain('1 crédit Sport Date par achat de ton filleul');
    expect(par('programme-credits-gerer')).not.toBeNull();

    expect(axios.get.mock.calls.length).toBe(getAvant);
    expect(axios.post.mock.calls.length).toBe(postAvant);
  });

  test('fermer (bouton, Échap, fond) : l\'assistant reste MONTÉ avec son état, focus rendu au raccourci', async () => {
    await monterCentre(ME_VIDE(), CONFIG_1);
    await act(async () => { par('wizard-suivant').click(); });
    const champ = par('wizard-message');
    await act(async () => { ecrire(champ, 'Viens danser avec moi dimanche !'); });
    const wizardAvant = par('invitation-wizard');

    // 1. bouton fermer
    await ouvrir('pass');
    expect(par('pass-preparer-invitation')).not.toBeNull();
    expect(par('invitation-wizard')).toBe(wizardAvant);    // rendu À CÔTÉ, pas à la place
    await act(async () => { par('drawer-fermer').click(); });
    expect(par('parrainage-drawer')).toBeNull();
    expect(document.activeElement).toBe(par('outil-pass'));

    // 2. Échap
    await ouvrir('historique');
    await touche('Escape');
    expect(par('parrainage-drawer')).toBeNull();
    expect(document.activeElement).toBe(par('outil-historique'));

    // 3. fond
    await ouvrir('invitations');
    await act(async () => { par('parrainage-drawer-fond').click(); });
    expect(par('parrainage-drawer')).toBeNull();

    expect(par('invitation-wizard')).toBe(wizardAvant);    // même nœud : jamais démonté
    expect(par('wizard-etape-2')).not.toBeNull();
    expect(par('wizard-message').value).toBe('Viens danser avec moi dimanche !');
  });

  test('« Préparer mon invitation » depuis le tiroir : le tiroir se ferme, l\'assistant reste là', async () => {
    await monterCentre(ME_VIDE());
    await ouvrir('pass');
    await act(async () => { par('pass-preparer-invitation').click(); });
    await act(async () => { await new Promise((r) => setTimeout(r, 5)); });
    expect(par('parrainage-drawer')).toBeNull();
    expect(par('invitation-wizard')).not.toBeNull();
  });

  test('Échap dans le sheet « Changer d\'offre » ferme le sheet, PAS le tiroir', async () => {
    await monterCentre(ME_PASS());
    await ouvrir('pass');
    await act(async () => { par('offre-changer').click(); });
    expect(par('offre-sheet')).not.toBeNull();
    await touche('Escape');
    expect(par('offre-sheet')).toBeNull();
    expect(par('parrainage-drawer')).not.toBeNull();
    await touche('Escape');
    expect(par('parrainage-drawer')).toBeNull();
  });

  test('le fond ne défile plus tant qu\'un tiroir est ouvert', async () => {
    await monterCentre(ME_PASS());
    await ouvrir('historique');
    expect(document.body.classList.contains('cp-scroll-lock')).toBe(true);
    await touche('Escape');
    expect(document.body.classList.contains('cp-scroll-lock')).toBe(false);
  });
});

describe('ParrainageDrawer — composant seul', () => {
  test('titre, bouton fermer libellé, contenu, onClose sur Échap', async () => {
    const onClose = jest.fn();
    await monter(<div className="cp-root"><ParrainageDrawer titre="Crédits" onClose={onClose}><p data-testid="dedans">ok</p></ParrainageDrawer></div>);
    expect(par('parrainage-drawer').textContent).toContain('Crédits');
    expect(par('dedans')).not.toBeNull();
    expect(par('drawer-fermer').getAttribute('aria-label')).toBe('Fermer');
    expect(document.activeElement).toBe(par('drawer-fermer'));   // focus posé dans le tiroir
    await touche('Escape');
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

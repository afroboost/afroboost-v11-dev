/**
 * PAR-2 — LOT 1 « INVITATION & PARRAINAGE » DANS L'ESPACE ABONNÉ.
 *
 * CE QU'IL PROUVE
 *   1. `statutInvitation` (règle pure) : « À partager » / « Partagée » /
 *      « Avantage débloqué », + « Ton ami a rejoint Afroboost », déduits des
 *      seuls champs publics du PassDTO de /me (status, invitee, invitations[]) ;
 *   2. InvitationParrainage : UN SEUL GET /me au montage ; le pass courant est
 *      rendu dans l'assistant EXISTANT avec son statut ; aucun e-mail ni
 *      téléphone de filleul n'est rendu ; sans pass → la création Pass Duo de
 *      l'assistant ; `onPass` (PUT /invitation) met l'état à jour sans relire /me ;
 *   3. CarteParrainage : sans `onOuvrir`, les deux boutons vont à /parrainage
 *      (inchangé) ; avec `onOuvrir`, « Invitation & parrainage » l'appelle ;
 *   4. SubscriberSpace : le bouton ouvre le tiroir, qui monte le parcours.
 *
 * axios est mocké : aucun réseau.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import InvitationParrainage, { statutInvitation } from '../InvitationParrainage';
import CarteParrainage from '../CarteParrainage';
import SubscriberSpace from '../../SubscriberSpace';
import { _resetParrainagePourTest, CLE_CACHE_PARRAINAGE } from '../../../utils/parrainage';

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('axios', () => ({
  __esModule: true,
  default: {
    get: jest.fn(), post: jest.fn(), put: jest.fn(), patch: jest.fn(), delete: jest.fn(),
    interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } },
  },
}));
jest.mock('qrcode.react', () => ({
  QRCodeSVG: (p) => <svg data-testid="qr-svg" data-value={p.value} />,
  QRCodeCanvas: (p) => <canvas data-testid="qr-canvas" data-value={p.value} />,
}));
jest.mock('../../ConditionsParticipation', () => () => null);
jest.mock('../../ConversionApresEssai', () => () => null);
jest.mock('../../SubscriberOnboarding', () => () => null);
jest.mock('../../SubscriberCockpit', () => () => null);
jest.mock('../../InvitationTemoignage', () => ({ __esModule: true, default: () => null, enRepos: () => false }));
jest.mock('../../Publications', () => ({ PublishModal: () => null }));
jest.mock('../../ui/dialog', () => ({
  Dialog: ({ children }) => children,
  DialogContent: ({ children }) => children,
  DialogTitle: ({ children }) => children,
}));

const CODE = 'AFR-PAR2AA';
const COURSE = { id: 'c1', name: 'Afroboost Dimanche', time: '18:30', locationName: 'Bord du Lac' };
const OCC = '2026-10-04T18:30:00';
const CONFIG = { enabled: true, courses: [{ ...COURSE, weekday: 0, date: '2026-10-04', occurrences: [OCC] }] };

function pass(status, extra) {
  return Object.assign({
    id: `p-${status}`, status, status_label: status, course: COURSE, occurrence: OCC,
    share_token: 'TOK123', invite_url: 'https://afroboost.com/duo/TOK123',
    share_url: 'https://afroboost.com/api/share/duo/TOK123',
    whatsapp_text: 'Rejoins-moi', invitee: null, tickets: [], invitation: { display_name: 'Ana', version: 0 },
    blocked_reason: null, created_at: '2026-09-28T10:00:00Z', unlocked_at: null, expires_at: OCC,
  }, extra || {});
}
function me(passes, invitations) {
  return { enabled: true, sponsor: { first_name: 'Ana', code: CODE }, stats: { invited: 0 },
    passes, invitations: invitations || [], history: [] };
}

let conteneur;
let racine;
const par = (id) => document.querySelector(`[data-testid="${id}"]`);
const appelsMe = () => axios.get.mock.calls.filter((c) => String(c[0]).endsWith('/referral/me')).length;
const attendre = () => act(async () => { for (let i = 0; i < 15; i += 1) await Promise.resolve(); });

/** Réponses GET par URL ; `meData` = la réponse de /me. */
function reseau(meData, espaceData) {
  axios.get.mockImplementation((url) => {
    const u = String(url);
    if (u.endsWith('/referral/me')) return Promise.resolve({ data: meData });
    if (u.endsWith('/referral/config')) return Promise.resolve({ data: CONFIG });
    if (u.endsWith('/referral/invitation')) return Promise.resolve({ data: { identity: { display_name: 'Ana' }, default_message: 'Viens !' } });
    if (u.includes('/subscriber/space/')) return Promise.resolve({ data: espaceData || {} });
    return Promise.reject({ response: { status: 404 } });
  });
}

async function monter(element) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  await act(async () => {
    racine = createRoot(conteneur);
    racine.render(element);
  });
  await attendre();
}

beforeEach(() => {
  jest.clearAllMocks();
  axios.get.mockReset(); axios.post.mockReset(); axios.put.mockReset();
  window.localStorage.clear();
  _resetParrainagePourTest();
  window.localStorage.setItem('afroboost_espace_token', JSON.stringify({
    token: 'jeton-de-banc', code: CODE, slug: '',
    expires_at: new Date(Date.now() + 30 * 86400000).toISOString(),
  }));
});
afterEach(() => {
  if (racine) act(() => racine.unmount());
  racine = null;
  if (conteneur) conteneur.remove();
  conteneur = null;
});

// ═══ 1. Règle pure ═══════════════════════════════════════════════════════════
describe('statutInvitation — champs publics du PassDTO seulement', () => {
  test('locked sans journal → À partager', () => {
    expect(statutInvitation(pass('locked'), [])).toEqual({ cle: 'a_partager', libelle: 'À partager', amiRejoint: false });
  });
  test('locked mais journalisé dans invitations[] → Partagée', () => {
    const s = statutInvitation(pass('locked'), [{ id: 'i1', pass_id: 'p-locked', channel: 'whatsapp' }]);
    expect(s.cle).toBe('partagee');
    expect(s.libelle).toBe('Partagée');
  });
  test('waiting → Partagée ; friend_registered → Partagée + ami rejoint', () => {
    expect(statutInvitation(pass('waiting'), []).cle).toBe('partagee');
    const s = statutInvitation(pass('friend_registered', { invitee: { first_name: 'Léa' } }), []);
    expect(s).toEqual({ cle: 'partagee', libelle: 'Partagée', amiRejoint: true });
  });
  test('unlocked / used → Avantage débloqué (+ ami rejoint si invitee)', () => {
    expect(statutInvitation(pass('unlocked', { invitee: { first_name: 'Léa' } }), [])).toEqual({ cle: 'debloque', libelle: 'Avantage débloqué', amiRejoint: true });
    expect(statutInvitation(pass('used'), []).cle).toBe('debloque');
  });
  test('pas de pass → null', () => {
    expect(statutInvitation(null, [])).toBeNull();
  });
});

// ═══ 2. InvitationParrainage ═════════════════════════════════════════════════
describe('InvitationParrainage — le même parcours, un seul GET /me', () => {
  test('pass courant affiché dans l\'assistant, statut « À partager », UN seul /me', async () => {
    reseau(me([pass('locked')]));
    await monter(<InvitationParrainage compact />);
    expect(appelsMe()).toBe(1);
    expect(par('invitation-parrainage')).not.toBeNull();
    expect(par('invitation-parrainage').closest('.cp-root')).not.toBeNull();
    expect(par('invitation-parrainage-statut').textContent).toContain('À partager');
    expect(par('wizard-prete')).not.toBeNull();       // l'assistant EXISTANT, pass ouvert
    expect(par('inviter-whatsapp')).not.toBeNull();
    expect(par('inviter-copier')).not.toBeNull();
    expect(par('inviter-qr')).not.toBeNull();
    const lien = par('invitation-parrainage-tout');
    expect(lien.getAttribute('href')).toBe('/parrainage');
    // Rien ne relance /me après coup.
    await attendre();
    expect(appelsMe()).toBe(1);
  });

  test('statut « Partagée » puis « Avantage débloqué » + « Ton ami a rejoint Afroboost »', async () => {
    reseau(me([pass('waiting')]));
    await monter(<InvitationParrainage />);
    expect(par('invitation-parrainage-statut').textContent).toContain('Partagée');
    expect(par('invitation-parrainage-ami')).toBeNull();
    act(() => racine.unmount()); racine = null; conteneur.remove();

    reseau(me([pass('unlocked', { invitee: { first_name: 'Léa' } })]));
    await monter(<InvitationParrainage />);
    expect(par('invitation-parrainage-statut').textContent).toContain('Avantage débloqué');
    expect(par('invitation-parrainage-ami').textContent).toContain('Ton ami a rejoint Afroboost');
  });

  test('aucune donnée privée du filleul n\'est rendue', async () => {
    const p = pass('friend_registered', {
      invitee: { first_name: 'Léa', email: 'lea.secret@example.com', whatsapp: '+41791234567', phone: '+41791234567' },
    });
    reseau(me([p]));
    await monter(<InvitationParrainage />);
    const texte = document.body.innerHTML;
    expect(texte).not.toContain('lea.secret@example.com');
    expect(texte).not.toContain('+41791234567');
    expect(texte).not.toContain('41791234567');
  });

  test('sans pass → la création Pass Duo de l\'assistant (règles inchangées)', async () => {
    reseau(me([]));
    await monter(<InvitationParrainage />);
    expect(appelsMe()).toBe(1);
    expect(par('invitation-parrainage-statut')).toBeNull();
    const wz = par('invitation-wizard');
    expect(wz).not.toBeNull();
    expect(wz.getAttribute('data-mode')).toBe('creation');
  });

  test('onPass (PUT /invitation) met l\'état à jour sans relire /me', async () => {
    reseau(me([pass('locked')]));
    const maj = pass('locked', { share_url: 'https://afroboost.com/api/share/duo/TOK123?v=2', invitation: { display_name: 'Ana B', version: 2 } });
    axios.put.mockResolvedValue({ data: maj });
    await monter(<InvitationParrainage />);
    await act(async () => { par('wizard-modifier').click(); });
    // V558 : une modification ouvre directement « Ta carte ».
    await act(async () => { par('wizard-enregistrer').click(); });
    await attendre();
    expect(axios.put).toHaveBeenCalledTimes(1);
    expect(par('wizard-prete')).not.toBeNull();
    expect(document.body.textContent).toContain('afroboost.com/api/share/duo/TOK123?v=2');
    expect(appelsMe()).toBe(1);
  });

  test('journal d\'un partage : locked → Partagée (POST /invitations, geste seulement)', async () => {
    reseau(me([pass('locked')]));
    axios.post.mockResolvedValue({ data: { id: 'inv-1' } });
    await monter(<InvitationParrainage />);
    const ouvrir = window.open; window.open = jest.fn();
    await act(async () => { par('inviter-whatsapp').click(); });
    await attendre();
    window.open = ouvrir;
    expect(axios.post.mock.calls[0][0]).toMatch(/\/referral\/invitations$/);
    expect(par('invitation-parrainage-statut').textContent).toContain('Partagée');
    expect(appelsMe()).toBe(1);
  });

  test('401/403 → ouvre ton espace ; désactivé → bientôt', async () => {
    axios.get.mockImplementation((url) => (String(url).endsWith('/referral/me')
      ? Promise.reject({ response: { status: 403 } }) : Promise.resolve({ data: CONFIG })));
    await monter(<InvitationParrainage />);
    expect(par('invitation-parrainage-non-connecte')).not.toBeNull();
    act(() => racine.unmount()); racine = null; conteneur.remove();

    axios.get.mockImplementation((url) => (String(url).endsWith('/referral/me')
      ? Promise.resolve({ data: { enabled: false } }) : Promise.resolve({ data: { enabled: false, courses: [] } })));
    _resetParrainagePourTest();
    await monter(<InvitationParrainage />);
    expect(par('invitation-parrainage-desactive')).not.toBeNull();
  });
});

// ═══ 3. CarteParrainage ══════════════════════════════════════════════════════
describe('CarteParrainage — prop onOuvrir facultative', () => {
  test('sans onOuvrir : les deux boutons vont à /parrainage (inchangé)', async () => {
    await monter(<CarteParrainage enabled />);
    expect(par('carte-parrainage-inviter').textContent).toBe('Inviter un ami');
    expect(par('carte-parrainage-ouvrir')).toBeNull();
    const avant = window.location.href;
    // jsdom ne navigue pas : on vérifie l'intention par la source du gestionnaire.
    const src = require('fs').readFileSync(require('path').join(__dirname, '..', 'CarteParrainage.js'), 'utf8');
    expect(src).toContain("window.location.href = '/parrainage'");
    expect(window.location.href).toBe(avant);
  });
  test('avec onOuvrir : « Invitation & parrainage » l\'appelle, « Voir mon Parrainage » reste', async () => {
    const onOuvrir = jest.fn();
    await monter(<CarteParrainage enabled onOuvrir={onOuvrir} />);
    const b = par('carte-parrainage-ouvrir');
    expect(b.textContent).toContain('Invitation & parrainage');
    await act(async () => { b.click(); });
    expect(onOuvrir).toHaveBeenCalledTimes(1);
    expect(onOuvrir.mock.calls[0][0]).toBe(b); // le déclencheur, pour y rendre le focus
    expect(par('carte-parrainage-voir')).not.toBeNull();
  });
  test('fermé : rien, même avec onOuvrir', async () => {
    await monter(<CarteParrainage enabled={false} onOuvrir={() => {}} />);
    expect(par('carte-parrainage')).toBeNull();
  });
});

// ═══ 4. SubscriberSpace ══════════════════════════════════════════════════════
describe('SubscriberSpace — le bouton ouvre le tiroir', () => {
  const ESPACE = {
    // Un WhatsApp : sans lui, l'onboarding V223 (mocké) remplace l'espace.
    subscriber: { name: 'Ana Dupont', code: CODE, whatsapp: '+41760000000' },
    subscription: { id: 'sub-1', code: CODE, offer_name: 'Forfait', total_sessions: 10, remaining_sessions: 5, used_sessions: 5 },
    coach: { name: 'Afroboost' },
    upcoming_courses: [],
    reservations: [],
  };

  test('« Invitation & parrainage » ouvre le tiroir avec le parcours ; /me n\'est lu qu\'à l\'ouverture', async () => {
    window.history.replaceState({}, '', `/espace/${CODE}`);
    window.localStorage.setItem(CLE_CACHE_PARRAINAGE, JSON.stringify({ enabled: true, courses: CONFIG.courses, ts: Date.now() }));
    reseau(me([pass('locked')]), ESPACE);
    await monter(<SubscriberSpace accessCode={CODE} />);
    const b = par('carte-parrainage-ouvrir');
    expect(b).not.toBeNull();
    expect(par('parrainage-drawer')).toBeNull();
    expect(appelsMe()).toBe(0);
    await act(async () => { b.click(); });
    await attendre();
    const tiroir = par('parrainage-drawer');
    expect(tiroir).not.toBeNull();
    expect(tiroir.closest('.cp-root')).not.toBeNull();
    expect(tiroir.querySelector('[data-testid="invitation-parrainage"]')).not.toBeNull();
    expect(appelsMe()).toBe(1);
    await act(async () => { par('drawer-fermer').click(); });
    expect(par('parrainage-drawer')).toBeNull();
  });

  test('parrainage fermé : ni carte, ni bouton', async () => {
    window.history.replaceState({}, '', `/espace/${CODE}`);
    window.localStorage.setItem(CLE_CACHE_PARRAINAGE, JSON.stringify({ enabled: false, courses: [], ts: Date.now() }));
    reseau(me([]), ESPACE);
    await monter(<SubscriberSpace accessCode={CODE} />);
    expect(par('carte-parrainage-ouvrir')).toBeNull();
    expect(appelsMe()).toBe(0);
  });
});


describe('PAR — intégration : partage par la chaîne', () => {
  it('chain_shared=true sans journal → « Partagée »', () => {
    const { statutInvitation: st } = require('../InvitationParrainage');
    expect(st({ id: 'p1', status: 'locked', chain_shared: true }, []).cle).toBe('partagee');
    expect(st({ id: 'p1', status: 'locked', chain_shared: false }, []).cle).toBe('a_partager');
  });
});


describe('PAR — intégration : ami_rejoint sans identité', () => {
  it('invitee null + ami_rejoint=true → « Ton ami a rejoint »', () => {
    const { statutInvitation: st } = require('../InvitationParrainage');
    const r = st({ id: 'p1', status: 'unlocked', invitee: null, ami_rejoint: true }, []);
    expect(r.amiRejoint).toBe(true);
    expect(st({ id: 'p1', status: 'locked', invitee: null, ami_rejoint: false }, []).amiRejoint).toBe(false);
  });
});

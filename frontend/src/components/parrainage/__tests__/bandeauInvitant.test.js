/**
 * L0 — IDENTITÉ DE L'INVITANT : qui invite, visible au moment du partage.
 *
 * CE QU'IL PROUVE
 *   1. BandeauInvitant : photo ronde + « Prénom t’invite à découvrir Afroboost » ;
 *      photo absente / refusée / en erreur → avatar Afroboost (jamais d'initiale) ;
 *      prénom absent → « Afroboost t’invite » ;
 *   2. photoAutorisee accepte https://res.cloudinary.com, refuse http / javascript / data ;
 *   3. WizardFilleul étape 2 : le bloc « Une dernière étape » AVANT le titre, et le
 *      bandeau (prénom saisi + child.inviter_display.photo_url) au-dessus du partage ;
 *   4. InvitationWizard (pass prêt) : bandeau au-dessus des boutons de partage ;
 *   5. InvitationDuo lit `inviter_display` (repli sponsor_*) ; avatar Afroboost sans photo.
 *
 * axios est mocké : aucun réseau.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import BandeauInvitant from '../BandeauInvitant';
import InvitationDuo from '../InvitationDuo';
import InvitationWizard from '../InvitationWizard';
import { photoAutorisee, MESSAGE_CHAINE_DEFAUT, _resetParrainagePourTest } from '../../../utils/parrainage';

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
const fetchOrigine = global.fetch;
beforeEach(() => {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  jest.clearAllMocks();
  axios.get.mockReset(); axios.post.mockReset(); axios.put.mockReset(); axios.patch.mockReset();
  window.localStorage.clear();
  window.localStorage.setItem('afroboost_subscriber_token', 'dev-1');
  _resetParrainagePourTest();
  global.fetch = undefined;
  window.open = jest.fn(() => null);
});
afterEach(() => {
  if (racine) act(() => racine.unmount());
  racine = null;
  conteneur.remove();
  global.fetch = fetchOrigine;
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const vider = () => act(async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); });
async function monter(element) {
  await act(async () => { racine = createRoot(conteneur); racine.render(element); });
  await vider();
}
const cliquer = async (id) => { await act(async () => { par(id).click(); }); await vider(); };

const PHOTO = 'https://res.cloudinary.com/dtm0r7hwq/image/upload/v1/profil.jpg';

// ═══ 1. Composant ═════════════════════════════════════════════════════════════
describe('L0 — BandeauInvitant', () => {
  test('avec photo : image ronde + « Prénom t’invite à découvrir Afroboost »', async () => {
    await monter(<BandeauInvitant prenom="Aïcha" photoUrl={PHOTO} />);
    expect(par('bandeau-photo').getAttribute('src')).toBe(PHOTO);
    expect(par('bandeau-avatar-afroboost')).toBeNull();
    expect(par('bandeau-texte').textContent).toBe('Aïcha t’invite à découvrir Afroboost');
  });

  test('sans photo : avatar Afroboost, jamais une initiale', async () => {
    await monter(<BandeauInvitant prenom="Aïcha" photoUrl={null} />);
    expect(par('bandeau-photo')).toBeNull();
    const av = par('bandeau-avatar-afroboost');
    expect(av).not.toBeNull();
    expect(av.getAttribute('src')).toBe('/logo192.png');
    expect(av.parentElement.textContent).toBe(''); // l'avatar ne porte aucune initiale
    expect(par('bandeau-texte').textContent).toBe('Aïcha t’invite à découvrir Afroboost');
  });

  test('photo refusée (http) : avatar Afroboost', async () => {
    await monter(<BandeauInvitant prenom="Aïcha" photoUrl="http://evil.example.com/a.jpg" />);
    expect(par('bandeau-photo')).toBeNull();
    expect(par('bandeau-avatar-afroboost')).not.toBeNull();
  });

  test('photo en erreur de chargement : avatar Afroboost', async () => {
    await monter(<BandeauInvitant prenom="Aïcha" photoUrl={PHOTO} />);
    await act(async () => { par('bandeau-photo').dispatchEvent(new Event('error')); });
    expect(par('bandeau-photo')).toBeNull();
    expect(par('bandeau-avatar-afroboost')).not.toBeNull();
  });

  test('sans prénom (ou un e-mail) : « Afroboost t’invite »', async () => {
    await monter(<BandeauInvitant prenom="" photoUrl={null} />);
    expect(par('bandeau-texte').textContent).toBe('Afroboost t’invite');
    act(() => racine.render(<BandeauInvitant prenom="x@y.ch" />));
    expect(par('bandeau-texte').textContent).toBe('Afroboost t’invite');
  });
});

// ═══ 2. photoAutorisee ════════════════════════════════════════════════════════
describe('L0 — photoAutorisee : Cloudinary', () => {
  test('https://res.cloudinary.com accepté ; http, javascript, data refusés', () => {
    expect(photoAutorisee(PHOTO)).toBe(PHOTO);
    expect(photoAutorisee('http://res.cloudinary.com/a.jpg')).toBeNull();
    expect(photoAutorisee('javascript:alert(1)')).toBeNull();
    expect(photoAutorisee('data:image/png;base64,AAAA')).toBeNull();
    expect(photoAutorisee('https://res.cloudinary.com.evil.com/a.jpg')).toBeNull();
  });
});

// ═══ 3. WizardFilleul étape 2 ═════════════════════════════════════════════════
const COURSE = { id: 'c1', name: 'Afroboost Dimanche', time: '18:30', locationName: 'Bord du Lac, Auvernier' };
const OCC = '2026-09-27T18:30:00';
const PUB = { status: 'waiting', sponsor_first_name: 'Bassi', course: COURSE, occurrence: OCC, expired: false, version: 1,
  chain_required: true, chain: { exists: false, shared: false } };
const CHILD = (extra) => Object.assign({
  share_token: 'T1', share_url: 'https://afroboost.com/api/share/duo/T1?v=3',
  invite_url: 'https://afroboost.com/duo/T1', card_url: 'https://afroboost.com/api/share/duo/T1/carte.jpg?v=h1',
  display_name: null, message: MESSAGE_CHAINE_DEFAUT, course: COURSE, occurrence: OCC,
}, extra || {});

function routerChaine(child) {
  axios.post.mockImplementation((url) => {
    if (String(url).endsWith('/chain')) {
      return Promise.resolve({ status: 201, data: { child, edit_key: 'K1', shared: false, preview: { ok: true } } });
    }
    return Promise.reject(new Error(`inattendu ${url}`));
  });
}

describe('L0 — WizardFilleul étapes « Ta carte » et « Partage » (V558)', () => {
  const versLaCarte = async () => { await cliquer('wf-continuer'); await cliquer('wf-seance-continuer'); };

  test('UX-P3 / V558 — les textes disent que les informations sont celles de la personne à l’écran, sans « a reçu »', async () => {
    routerChaine(CHILD());
    axios.get.mockResolvedValue({ data: PUB });
    await monter(<InvitationDuo token="T0" />);
    await versLaCarte();
    const bloc = par('wf-derniere-etape');
    expect(bloc).not.toBeNull();
    const h2 = par('wf-etape-carte').querySelector('h2');
    expect(h2.textContent).toBe('Personnalise ton invitation');
    expect(bloc.textContent).toContain('Ce sont TES informations. Ton ami verra qui l’invite.');
    const t = par('wf-etape-carte').textContent;
    expect(t).toContain('Tes informations');
    expect(t).toContain('Ces informations apparaîtront sur l’invitation envoyée à ton ami.');
    expect(t).toContain('Aperçu de ce que ton ami recevra');
    expect(t).toContain('C’est ton numéro, pas celui de la personne que tu invites.');
    expect(t).not.toMatch(/a reçu/);
    await cliquer('wf-carte-continuer');
    const t4 = par('wf-etape-partage').textContent;
    expect(t4).toContain('Envoie ton invitation');
    expect(t4).toContain('Ton ami recevra cette invitation et renseignera ses propres informations quand il l’ouvrira.');
    // le titre précède les boutons de partage
    // eslint-disable-next-line no-bitwise
    expect(par('wf-maintenant').compareDocumentPosition(par('wf-whatsapp')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(t4).not.toMatch(/a reçu/);
  });

  test('aperçu : photo de child.inviter_display, prénom saisi, badge du type ; puis les boutons de partage', async () => {
    routerChaine(CHILD({ display_name: 'Henri', inviter_display: { prenom: 'Henri', photo_url: PHOTO, source: 'member' } }));
    axios.get.mockResolvedValue({ data: PUB });
    await monter(<InvitationDuo token="T0" />);
    await versLaCarte();
    const bandeau = par('bandeau-invitant');
    expect(bandeau).not.toBeNull();
    expect(par('bandeau-photo').getAttribute('src')).toBe(PHOTO);
    expect(par('bandeau-texte').textContent).toBe('Henri t’invite à découvrir Afroboost');
    expect(par('wf-apercu-type')).not.toBeNull();
    await cliquer('wf-carte-continuer');
    expect(par('wf-whatsapp')).not.toBeNull();
  });

  test('sans inviter_display ni prénom : avatar Afroboost et « Afroboost t’invite »', async () => {
    routerChaine(CHILD());
    axios.get.mockResolvedValue({ data: PUB });
    await monter(<InvitationDuo token="T0" />);
    await versLaCarte();
    expect(par('bandeau-avatar-afroboost')).not.toBeNull();
    expect(par('bandeau-texte').textContent).toBe('Afroboost t’invite');
  });
});

// ═══ 4. InvitationWizard (membre) ═════════════════════════════════════════════
describe('L0 — InvitationWizard : bandeau au partage', () => {
  test('pass prêt : bandeau (identité préremplie) avant WhatsApp', async () => {
    axios.get.mockImplementation((url) => {
      const u = String(url);
      if (u.endsWith('/spordate/unified-profile/me')) return Promise.resolve({ data: { lie: false } });
      if (u.endsWith('/referral/invitation')) {
        return Promise.resolve({ data: { identity: { display_name: 'Aïcha', photo_url: PHOTO }, default_message: 'Salut', pass: null } });
      }
      return Promise.resolve({ data: {} });
    });
    const p = { id: 'p1', status: 'locked', course: COURSE, occurrence: OCC, share_token: 'TOK',
      share_url: 'https://afroboost.com/api/share/duo/TOK', invitation: { version: 0 } };
    await monter(<InvitationWizard courses={[]} passOuvert={p} />);
    const bandeau = par('bandeau-invitant');
    expect(bandeau).not.toBeNull();
    expect(par('bandeau-texte').textContent).toBe('Aïcha t’invite à découvrir Afroboost');
    expect(par('bandeau-photo').getAttribute('src')).toBe(PHOTO);
    // eslint-disable-next-line no-bitwise
    expect(bandeau.compareDocumentPosition(par('inviter-whatsapp')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

// ═══ 5. InvitationDuo (invité) ════════════════════════════════════════════════
describe('L0 — InvitationDuo lit inviter_display', () => {
  const PUB_SIMPLE = { status: 'waiting', sponsor_first_name: 'Bassi', course: COURSE, occurrence: OCC, expired: false };
  test('inviter_display prime sur sponsor_* (prénom + photo)', async () => {
    axios.get.mockResolvedValue({ data: { ...PUB_SIMPLE, sponsor_display_name: 'Ancien nom',
      inviter_display: { prenom: 'Coralie', photo_url: PHOTO, source: 'member' } } });
    await monter(<InvitationDuo token="TOK" />);
    expect(par('invitation-de').textContent).toContain('Invitation de Coralie');
    expect(par('invitation-photo').getAttribute('src')).toBe(PHOTO);
  });
  test('sans photo : avatar Afroboost (pas d’initiale)', async () => {
    axios.get.mockResolvedValue({ data: { ...PUB_SIMPLE, inviter_display: { prenom: 'Coralie', photo_url: null, source: 'member' } } });
    await monter(<InvitationDuo token="TOK" />);
    expect(par('invitation-photo')).toBeNull();
    expect(par('invitation-avatar-afroboost').getAttribute('src')).toBe('/logo192.png');
  });
  test('repli sponsor_photo_url quand inviter_display est absent', async () => {
    axios.get.mockResolvedValue({ data: { ...PUB_SIMPLE, sponsor_photo_url: PHOTO } });
    await monter(<InvitationDuo token="TOK" />);
    expect(par('invitation-photo').getAttribute('src')).toBe(PHOTO);
    expect(par('invitation-de').textContent).toContain('Invitation de Bassi');
  });
  test('parcours chaîne, étape 1 : avatar Afroboost au lieu de l’initiale', async () => {
    axios.get.mockResolvedValue({ data: { ...PUB, inviter_display: { prenom: 'Coralie', photo_url: null, source: 'member' } } });
    await monter(<InvitationDuo token="T0" />);
    expect(par('wf-etape-1')).not.toBeNull();
    expect(par('invitation-avatar-afroboost')).not.toBeNull();
    expect(par('invitation-de').textContent).toContain("Coralie t'invite");
  });
});

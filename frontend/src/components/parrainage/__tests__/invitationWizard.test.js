/**
 * V551 — PARRAINAGE V2 : l'assistant d'invitation du membre.
 * V558 — le MÊME Wizard que le filleul : Offre · Séance · Ta carte · Partage.
 *
 * CE QU'IL PROUVE
 *   1. préremplissage du nom et de la photo depuis le profil Spordateur lié
 *      (GET /api/spordate/unified-profile/me, en-tête du parrain) ;
 *   2. un e-mail n'est JAMAIS affiché comme nom (ni depuis le profil, ni depuis
 *      /invitation) → « Afroboost » (V558 : jamais « Un membre ») ;
 *   3. « Modifier » ne touche QUE l'invitation : aucune route de profil appelée,
 *      le nom modifié part dans `invitation` du POST /pass ;
 *   4. pass existant → AUCUN POST /pass ; « Modifier » fait un PUT
 *      /pass/{id}/invitation ; le jeton reste le même, le nouveau `share_url`
 *      (?v=) est celui qu'on partage ;
 *   5. trois étapes au plus ;
 *   6. WhatsApp, Partager et Copier utilisent le `share_url` renvoyé.
 *
 * axios est mocké : aucun réseau.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import InvitationWizard from '../InvitationWizard';
import InvitationDuo from '../InvitationDuo';
import {
  nomAffichable, photoAutorisee, identitePreremplie, lireContexteUrl, corpsInvitation,
  NOM_NEUTRE, MESSAGE_MAX, _resetParrainagePourTest,
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

let conteneur, racine;
beforeEach(() => {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  jest.clearAllMocks();
  axios.get.mockReset(); axios.post.mockReset(); axios.put.mockReset(); axios.patch.mockReset();
  window.localStorage.clear();
  window.localStorage.setItem('afroboost_subscriber_token', 'dev-1');
  _resetParrainagePourTest();
});
afterEach(() => {
  if (racine) act(() => racine.unmount());
  racine = null;
  conteneur.remove();
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
async function flush() {
  await act(async () => { for (let i = 0; i < 10; i += 1) await Promise.resolve(); });
}
async function monter(element) {
  await act(async () => { racine = createRoot(conteneur); racine.render(element); });
  await flush();
}
// V562 : un seul type membre → l'étape Offre est sautée ; on ouvre sur « Séance ».
const versLaCarte = async () => { await cliquer('wizard-suivant'); };
async function cliquer(id) {
  const el = par(id);
  if (!el) throw new Error(`élément absent : ${id}`);
  await act(async () => { el.click(); });
  await flush();
}
function saisir(el, valeur) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set;
  act(() => {
    setter.call(el, valeur);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

const COURSE = { id: 'c1', name: 'Afroboost Dimanche', locationName: 'Bord du Lac' };
const OCC = '2026-10-04T18:30:00';
const OCC2 = '2026-10-11T18:30:00';
const COURSES = [{ ...COURSE, occurrences: [OCC, OCC2], offers: [
  { id: 'o1', name: 'Essai offert', price: 0, recommended: true },
  { id: 'o2', name: 'Séance 30', price: 30 },
] }];
const PROFIL_LIE = { lie: true, profil: { displayName: 'Aïcha', photoURL: 'https://firebasestorage.googleapis.com/v0/b/x/o/a.jpg', photos: [] } };
const INVITATION = { identity: { display_name: 'Aïcha B', photo_url: null }, default_message: 'Viens danser avec moi !', pass: null };

function passOuvert(extra) {
  return Object.assign({
    id: 'p1', status: 'locked', course: COURSE, occurrence: OCC, share_token: 'TOK123',
    invite_url: 'https://afroboost.com/duo/TOK123', share_url: 'https://afroboost.com/api/share/duo/TOK123',
    whatsapp_text: 'Rejoins-moi https://afroboost.com/api/share/duo/TOK123',
    invitation: { display_name: null, photo_url: null, message: null, version: 0 },
  }, extra || {});
}

function routerGet({ profil, invitation } = {}) {
  axios.get.mockImplementation((url) => {
    const u = String(url);
    if (u.endsWith('/spordate/unified-profile/me')) return Promise.resolve({ data: profil || { lie: false } });
    if (u.endsWith('/referral/invitation')) return Promise.resolve({ data: invitation || INVITATION });
    return Promise.resolve({ data: {} }); // /terms/active et autres : rien d'exigé
  });
}
const routesProfilEcrites = () => []
  .concat(axios.put.mock.calls, axios.patch.mock.calls, axios.post.mock.calls)
  .filter((c) => /spordate|unified-profile|subscriber|profile/.test(String(c[0])));

// ═══ Fonctions pures ═════════════════════════════════════════════════════════
describe('V551 — filtres purs', () => {
  test('nomAffichable refuse un e-mail, un identifiant, garde un vrai prénom', () => {
    expect(nomAffichable('aicha@gmail.com')).toBe('');
    expect(nomAffichable('   ')).toBe('');
    expect(nomAffichable('12345')).toBe('');
    expect(nomAffichable('abcdefghijklmnopqrstuvwxyz')).toBe('');
    expect(nomAffichable('Aïcha')).toBe('Aïcha');
  });
  test('photoAutorisee : https sur les hôtes du contrat ou /api/files, sinon null', () => {
    expect(photoAutorisee('https://firebasestorage.googleapis.com/a.jpg')).toBeTruthy();
    expect(photoAutorisee('/api/files/abc/photo.jpg')).toBeTruthy();
    expect(photoAutorisee('http://afroboost.com/a.jpg')).toBeNull();
    expect(photoAutorisee('https://evil.example.com/a.jpg')).toBeNull();
    expect(photoAutorisee('javascript:alert(1)')).toBeNull();
  });
  test('identitePreremplie : profil lié d\'abord ; override du pass prioritaire ; e-mail jamais', () => {
    expect(identitePreremplie({ profil: PROFIL_LIE.profil, identity: INVITATION.identity }).nom).toBe('Aïcha');
    expect(identitePreremplie({ profil: { displayName: 'x@y.ch' }, identity: { display_name: 'z@y.ch' } }).nom).toBe('');
    const p = passOuvert({ invitation: { display_name: 'Aïcha la danseuse', photo_url: null, message: 'Hey', version: 2 } });
    const id = identitePreremplie({ pass: p, profil: PROFIL_LIE.profil });
    expect(id.nom).toBe('Aïcha la danseuse');
    expect(id.photo).toBeNull(); // retirée par le membre : on respecte
  });
  test('lireContexteUrl lit ?course=&occurrence=&offer=', () => {
    expect(lireContexteUrl('?course=c1&occurrence=2026-10-11T18%3A30%3A00&offer=o2'))
      .toEqual({ course: 'c1', occurrence: OCC2, offer: 'o2' });
  });
  test('corpsInvitation : jamais de nom e-mail, message borné', () => {
    const c = corpsInvitation({ nom: 'a@b.ch', photo: 'https://evil.example.com/x.jpg', message: 'x'.repeat(400) });
    expect(c.display_name).toBeUndefined();
    expect(c.photo_url).toBeNull();
    expect(c.message.length).toBe(MESSAGE_MAX);
  });
});

// ═══ Création (aucun pass) ═══════════════════════════════════════════════════
describe('V551 — InvitationWizard : création en 3 étapes', () => {
  test('préremplit nom + photo depuis unified-profile (avec l\'en-tête du parrain)', async () => {
    routerGet({ profil: PROFIL_LIE });
    await monter(<InvitationWizard courses={COURSES} passOuvert={null} />);
    const appelProfil = axios.get.mock.calls.find((c) => String(c[0]).endsWith('/spordate/unified-profile/me'));
    expect(appelProfil).toBeTruthy();
    expect(appelProfil[1].headers).toEqual({ 'X-Subscriber-Token': 'dev-1' });
    expect(par('wf-seance-resume')).not.toBeNull(); // V558 : le résumé de la séance (calendrier existant)
    expect(par('pass-select-seance')).toBeNull();
    await cliquer('wizard-suivant');
    expect(par('wizard-champ-nom').value).toBe('Aïcha');
    expect(par('carte-invitation-titre').textContent).toBe('Aïcha t’invite à découvrir Afroboost');
    expect(par('carte-invitation-photo').getAttribute('src')).toBe(PROFIL_LIE.profil.photoURL);
  });

  test('un e-mail comme nom est refusé → nom neutre + initiale', async () => {
    routerGet({ profil: { lie: true, profil: { displayName: 'aicha.b@gmail.com', photoURL: null } },
      invitation: { identity: { display_name: 'aicha.b@gmail.com' }, default_message: '', pass: null } });
    await monter(<InvitationWizard courses={COURSES} passOuvert={null} />);
    await versLaCarte();
    expect(par('carte-invitation-titre').textContent).toBe('Afroboost t’invite à essayer un cours');
    expect(NOM_NEUTRE).toBe('Afroboost');
    expect(par('carte-invitation-titre').textContent).not.toContain('@');
    expect(par('carte-invitation-photo')).toBeNull();
    expect(par('carte-invitation-logo')).not.toBeNull();
  });

  test('V562 : Offre sautée (un seul type) → 3 étapes (Séance · Ta carte · Partage) ; « Modifier » ne touche QUE l\'invitation ; POST /pass porte `invitation`', async () => {
    routerGet({ profil: PROFIL_LIE });
    const cree = passOuvert({ share_url: 'https://afroboost.com/api/share/duo/TOK123?v=1',
      invitation: { display_name: 'Aïcha la reine', photo_url: null, message: 'Viens danser avec moi !', version: 1 } });
    axios.post.mockResolvedValue({ data: cree });
    const onPass = jest.fn();
    await monter(<InvitationWizard courses={COURSES} passOuvert={null} onPass={onPass} />);
    expect(par('wizard-etapes').children.length).toBe(3);
    expect(par('wizard-etapes').textContent.replace(/\s+/g, '')).toBe('1Séance2Tacarte3Partage');
    expect(par('wizard-etape-1')).toBeNull(); // un seul type : choisi d'office, jamais affiché
    expect(par('wizard-precedent')).toBeNull();

    // Étape 2 : la séance (résumé compact + « Changer de séance »)
    expect(par('wizard-etape-2')).not.toBeNull();
    expect(par('wf-seance-changer')).not.toBeNull();
    await cliquer('wizard-suivant');

    // Étape 3 : TES informations + message + aperçu réel
    expect(par('wizard-etape-3')).not.toBeNull();
    expect(par('wizard-suivant')).toBeNull(); // la 4e étape est le partage, après la création
    saisir(par('wizard-champ-nom'), 'Aïcha la reine');
    await cliquer('wizard-photo-retirer');
    await cliquer('wizard-modifier-message'); // V560 : le message est replié par défaut
    expect(par('wizard-message').value).toBe('Viens danser avec moi !');
    expect(par('wizard-compteur').textContent).toContain(`/${MESSAGE_MAX}`);
    expect(Number(par('wizard-message').getAttribute('maxLength'))).toBe(MESSAGE_MAX);
    expect(par('wizard-apercu').textContent).toContain('Aïcha la reine t’invite à découvrir Afroboost');
    expect(document.querySelectorAll('[data-testid="carte-invitation-titre"]')).toHaveLength(1);
    await cliquer('wizard-creer');

    expect(axios.post).toHaveBeenCalledTimes(1);
    const [url, corps] = axios.post.mock.calls[0];
    expect(String(url)).toMatch(/\/referral\/pass$/);
    expect(corps.course_id).toBe('c1');
    expect(corps.occurrence).toBe(OCC);
    expect(corps.offer_id).toBe('o1');
    expect(corps.invitation).toEqual({ display_name: 'Aïcha la reine', photo_url: null, message: 'Viens danser avec moi !' });
    expect(routesProfilEcrites()).toEqual([]); // AUCUNE route de profil touchée
    expect(onPass).toHaveBeenCalledWith(cree);
  });

  test('contexte d\'URL : séance et offre présélectionnées', async () => {
    routerGet();
    axios.post.mockResolvedValue({ data: passOuvert() });
    await monter(<InvitationWizard courses={COURSES} passOuvert={null} contexte={{ course: 'c1', occurrence: OCC2, offer: 'o2' }} />);
    expect(par('wf-seance-resume')).not.toBeNull();
    await cliquer('wizard-suivant');
    await cliquer('wizard-creer');
    expect(axios.post.mock.calls[0][1].occurrence).toBe(OCC2);
    expect(axios.post.mock.calls[0][1].offer_id).toBe('o2');
  });
});

// ═══ Pass existant ═══════════════════════════════════════════════════════════
describe('V551 — InvitationWizard : pass existant', () => {
  test('« Ton invitation est prête » : aucun POST /pass ; WhatsApp / Partager / Copier utilisent share_url', async () => {
    routerGet({ profil: PROFIL_LIE });
    const p = passOuvert({ share_url: 'https://afroboost.com/api/share/duo/TOK123?v=3', whatsapp_text: null });
    const onJournal = jest.fn();
    const ouvrir = jest.spyOn(window, 'open').mockImplementation(() => null);
    const ecrire = jest.fn().mockResolvedValue();
    const partage = jest.fn().mockResolvedValue();
    Object.assign(navigator, { clipboard: { writeText: ecrire }, share: partage });
    await monter(<InvitationWizard courses={COURSES} passOuvert={p} onJournal={onJournal} />);
    expect(par('wizard-prete').textContent).toContain('Partage ton invitation');
    expect(par('wizard-apercu')).not.toBeNull();

    await cliquer('inviter-whatsapp');
    expect(String(ouvrir.mock.calls[0][0])).toContain(encodeURIComponent('https://afroboost.com/api/share/duo/TOK123?v=3'));
    await cliquer('inviter-partager');
    expect(partage.mock.calls[0][0].url).toBe('https://afroboost.com/api/share/duo/TOK123?v=3');
    await cliquer('inviter-copier');
    expect(ecrire).toHaveBeenCalledWith('https://afroboost.com/api/share/duo/TOK123?v=3');
    expect(onJournal.mock.calls.map((c) => c[1])).toEqual(['whatsapp', 'share', 'copy']);
    expect(axios.post).not.toHaveBeenCalled();
    ouvrir.mockRestore();
    delete navigator.share;
  });

  test('pass renvoyé par /invitation seulement : pas de création non plus', async () => {
    routerGet({ invitation: { identity: { display_name: 'Aïcha' }, default_message: 'Salut', pass: passOuvert() } });
    await monter(<InvitationWizard courses={COURSES} passOuvert={null} />);
    expect(par('wizard-prete')).not.toBeNull();
    expect(par('wizard-creer')).toBeNull();
  });

  test('Modifier → PUT /pass/{id}/invitation, même jeton, le nouveau ?v= est partagé', async () => {
    routerGet({ profil: PROFIL_LIE });
    const p = passOuvert();
    const apres = passOuvert({ share_url: 'https://afroboost.com/api/share/duo/TOK123?v=1',
      whatsapp_text: 'On bouge ! \nhttps://afroboost.com/api/share/duo/TOK123?v=1',
      invitation: { display_name: 'Aïcha', photo_url: null, message: 'On bouge !', version: 1 } });
    axios.put.mockResolvedValue({ data: apres });
    const onPass = jest.fn();
    const ouvrir = jest.spyOn(window, 'open').mockImplementation(() => null);
    const { rerender } = { rerender: (el) => act(() => racine.render(el)) };
    await monter(<InvitationWizard courses={COURSES} passOuvert={p} onPass={onPass} />);
    await cliquer('wizard-modifier');
    // V558 : une modification ouvre directement « Ta carte » (étape 3 du même Wizard).
    expect(par('wizard-etape-3')).not.toBeNull();
    expect(par('pass-select-seance')).toBeNull(); // la séance se change dans la carte du Pass (V539b)
    expect(par('wf-seance-resume')).toBeNull();
    saisir(par('wizard-message'), 'On bouge !');
    await cliquer('wizard-enregistrer');

    expect(axios.post).not.toHaveBeenCalled();
    expect(axios.put).toHaveBeenCalledTimes(1);
    const [url, corps] = axios.put.mock.calls[0];
    expect(String(url)).toMatch(/\/referral\/pass\/p1\/invitation$/);
    expect(corps.message).toBe('On bouge !');
    expect(corps.display_name).toBe('Aïcha');
    expect(JSON.stringify(corps)).not.toContain('TOK123'); // le jeton ne se négocie pas
    expect(routesProfilEcrites()).toEqual([]);
    expect(onPass).toHaveBeenCalledWith(apres);
    expect(apres.share_token).toBe(p.share_token);

    rerender(<InvitationWizard courses={COURSES} passOuvert={apres} onPass={onPass} />);
    await flush();
    await cliquer('inviter-whatsapp');
    expect(String(ouvrir.mock.calls[0][0])).toContain(encodeURIComponent('https://afroboost.com/api/share/duo/TOK123?v=1'));
    ouvrir.mockRestore();
  });
});

// ═══ V552 — la vraie carte (og:image) dans l'aperçu ══════════════════════════
const CARTE = 'https://afroboost.com/api/share/duo/TOK123/carte.jpg?v=2';
describe('V560 — InvitationWizard : UNE carte, rendue en direct', () => {
  test('« prête » : la carte HTML (prénom, photo, type, séance, lieu), sans image ni bandeau en double', async () => {
    routerGet({ profil: PROFIL_LIE });
    const p = passOuvert({ card_url: CARTE, invitation: { display_name: 'Aïcha', photo_url: null, message: 'On danse ?', version: 2 } });
    await monter(<InvitationWizard courses={COURSES} passOuvert={p} />);
    const carte = par('wizard-apercu');
    expect(carte.textContent).toContain('Aïcha t’invite à découvrir Afroboost');
    expect(carte.textContent).toContain('Pass Duo');
    expect(carte.textContent).toContain('Afroboost Dimanche');
    expect(carte.textContent).toContain('Bord du Lac');
    expect(conteneur.querySelector(`img[src="${CARTE}"]`)).toBeNull();
    expect(par('bandeau-invitant')).toBeNull();
  });

  test('modification : « Ta carte » directement, la carte suit la frappe du prénom', async () => {
    routerGet({ profil: PROFIL_LIE });
    await monter(<InvitationWizard courses={COURSES} passOuvert={passOuvert({ card_url: CARTE })} />);
    await cliquer('wizard-modifier');
    expect(par('wizard-etape-3')).not.toBeNull();
    saisir(par('wizard-champ-nom'), 'Coralie');
    await flush();
    expect(par('carte-invitation-titre').textContent).toBe('Coralie t’invite à découvrir Afroboost');
    expect(par('wizard-message')).not.toBeNull(); // en modification, le message est ouvert
  });
});

// ═══ V552 — cibles tactiles ≥ 44 px ══════════════════════════════════════════
describe('V552 — InvitationWizard : cibles tactiles', () => {
  test('Modifier et QR portent la classe de cible tactile ; les boutons pleins aussi', async () => {
    routerGet({ profil: PROFIL_LIE });
    await monter(<InvitationWizard courses={COURSES} passOuvert={passOuvert()} onQr={jest.fn()} />);
    expect(par('wizard-modifier').classList.contains('cp-wz-tap')).toBe(true);
    expect(par('inviter-qr').classList.contains('cp-wz-tap')).toBe(true);
    ['inviter-whatsapp', 'inviter-partager', 'inviter-copier'].forEach((id) => {
      expect(par(id).classList.contains('cp-wz-cible')).toBe(true);
    });
    await cliquer('wizard-modifier');
    expect(par('wizard-enregistrer').classList.contains('cp-wz-cible')).toBe(true);
    expect(par('wizard-annuler').classList.contains('cp-wz-tap')).toBe(true);
  });

  test('création : Continuer / Retour / Créer portent la cible tactile ; la séance se change dans le calendrier', async () => {
    routerGet({ profil: PROFIL_LIE });
    await monter(<InvitationWizard courses={COURSES} passOuvert={null} />);
    expect(par('wizard-suivant').classList.contains('cp-wz-cible')).toBe(true);
    expect(par('wf-seance-changer').classList.contains('cp-wz-tap')).toBe(true);
    await cliquer('wizard-suivant');
    expect(par('wizard-precedent').classList.contains('cp-wz-cible')).toBe(true);
    expect(par('wizard-creer').classList.contains('cp-wz-cible')).toBe(true);
  });
});

// ═══ Page invité ═════════════════════════════════════════════════════════════
describe('V551 — InvitationDuo : nom et photo de l\'invitation', () => {
  const PUB = { status: 'waiting', sponsor_first_name: 'Bassi', course: COURSE, occurrence: OCC, expired: false };
  test('sponsor_display_name remplace le prénom ; photo affichée si fournie', async () => {
    axios.get.mockResolvedValue({ data: { ...PUB, sponsor_display_name: 'Bassi le coach', sponsor_photo_url: 'https://afroboost.com/p.jpg' } });
    await monter(<InvitationDuo token="TOK123" />);
    expect(par('invitation-de').textContent).toContain('Invitation de Bassi le coach');
    expect(par('invitation-photo').getAttribute('src')).toBe('https://afroboost.com/p.jpg');
  });
  test('un e-mail n\'est jamais affiché, même s\'il arrivait du serveur', async () => {
    axios.get.mockResolvedValue({ data: { ...PUB, sponsor_display_name: 'bassi@x.ch', sponsor_first_name: 'bassi@x.ch' } });
    await monter(<InvitationDuo token="TOK123" />);
    expect(par('invitation-de').textContent).not.toContain('@');
  });
  test('sans sponsor_display_name : le prénom existant, comme avant', async () => {
    axios.get.mockResolvedValue({ data: PUB });
    await monter(<InvitationDuo token="TOK123" />);
    expect(par('invitation-de').textContent).toContain('Invitation de Bassi');
    expect(par('invitation-photo')).toBeNull();
  });
});

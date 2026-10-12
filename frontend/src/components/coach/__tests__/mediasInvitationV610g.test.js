/**
 * V610g — médias de l'invitation : lecteur audio Afroboost, outil vidéo EXISTANT réutilisé
 * (découpe / formats / « Capturer cette image comme miniature »), vignette de « Mes
 * invitations », vidéo publique sans bouton « Télécharger ».
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn(), create: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } }));
jest.mock('../InvitationMiniature', () => function Mini() { return null; });
jest.mock('../../CloudinaryUploadButton', () => ({ uploadToCloudinary: jest.fn(() => Promise.resolve({ url: 'https://res.cloudinary.com/dtm0r7hwq/image/upload/v1/invitations/capture.jpg' })) }));
// L'outil EXISTANT est simulé : on vérifie qu'il est OUVERT avec la vidéo et que ses deux
// sorties (miniature capturée, version exportée) arrivent bien sur l'invitation.
jest.mock('../prospection/ProspectionVideoEditeur', () => function OutilSimule(p) {
  return (
    <div data-testid="outil-existant" data-url={p.original.url} data-titre={p.titre}>
      <button type="button" data-testid="outil-capturer"
              onClick={() => p.enregistrerMiniature(new File(['x'], 'mini.jpg', { type: 'image/jpeg' })).catch((e) => { globalThis.__errCapture = String(e); })}>Capturer cette image comme miniature</button>
      <button type="button" data-testid="outil-fermer" onClick={p.onFermer}>Fermer</button>
    </div>
  );
});
// eslint-disable-next-line import/first
import axios from 'axios';
// eslint-disable-next-line import/first
import { uploadToCloudinary } from '../../CloudinaryUploadButton';
// eslint-disable-next-line import/first
import AfroboostAudioPlayer, { ondeDepuis, temps, VITESSES } from '../../AfroboostAudioPlayer';
// eslint-disable-next-line import/first
import ChoixMedia, { instantApercu } from '../ChoixMedia';
// eslint-disable-next-line import/first
import { sourcesVignette } from '../MesInvitations';
// eslint-disable-next-line import/first
import EditeurInvitation from '../EditeurInvitation';
// eslint-disable-next-line import/first
import InvitationPublique from '../../InvitationPublique';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let conteneur = null; let racine = null;
function render(el) { conteneur = document.createElement('div'); document.body.appendChild(conteneur); racine = createRoot(conteneur); racine.render(el); return { container: conteneur }; }
afterEach(() => { if (racine) act(() => racine.unmount()); if (conteneur) conteneur.remove(); racine = null; conteneur = null; jest.clearAllMocks(); });
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
async function attendre(fn) { let e; for (let i = 0; i < 40; i += 1) { try { fn(); return; } catch (x) { e = x; } await act(async () => { await new Promise((r) => setTimeout(r, 25)); }); } throw e; }

describe('V610g — AfroboostAudioPlayer', () => {
  let play; let pause;
  beforeEach(() => {
    play = jest.spyOn(window.HTMLMediaElement.prototype, 'play').mockImplementation(function () { Object.defineProperty(this, 'paused', { configurable: true, get: () => false }); return Promise.resolve(); });
    pause = jest.spyOn(window.HTMLMediaElement.prototype, 'pause').mockImplementation(function () { Object.defineProperty(this, 'paused', { configurable: true, get: () => true }); });
  });
  afterEach(() => { play.mockRestore(); pause.mockRestore(); });

  test('capsule : jamais d’autoplay, lecture / pause / reprise, vitesse 1x -> 1.25x -> 1.5x -> 2x -> 1x', async () => {
    await act(async () => { render(<AfroboostAudioPlayer src="/api/files/a1/m.mp3" testidAudio="aud" testidBouton="btn" />); });
    expect(q('aud').autoplay).toBe(false);
    expect(q('aud').getAttribute('preload')).toBe('none');
    expect(q('aud').hasAttribute('controls')).toBe(false);          // plus de lecteur natif gris
    expect(q('btn').textContent).toMatch(/Écouter le message/);
    expect(play).not.toHaveBeenCalled();
    await act(async () => { q('btn').click(); });
    expect(play).toHaveBeenCalledTimes(1);
    expect(q('btn').textContent).toMatch(/Pause/);
    await act(async () => { q('btn').click(); });
    expect(q('btn').textContent).toMatch(/Reprendre le message/);
    expect(q('afroboost-audio-vitesse').textContent).toBe('1x');
    for (const v of VITESSES.slice(1).concat([1])) { await act(async () => { q('afroboost-audio-vitesse').click(); }); expect(q('afroboost-audio-vitesse').textContent).toBe(`${v}x`); }
    expect(q('afroboost-audio-onde').children.length).toBe(36);
    expect(q('afroboost-audio-temps')).toBeTruthy();
  });
  test('onde stable par fichier et temps lisible', () => {
    expect(ondeDepuis('/a.mp3')).toEqual(ondeDepuis('/a.mp3'));
    expect(ondeDepuis('/a.mp3')).not.toEqual(ondeDepuis('/b.mp3'));
    expect(temps(14.4)).toBe('0:14'); expect(temps(75)).toBe('1:15');
  });
});

describe('V610g — outil vidéo existant + miniature', () => {
  test('ChoixMedia vidéo : « Découper / Modifier / exporter » seulement avec une vidéo ; audio = lecteur Afroboost', async () => {
    const ouvrir = jest.fn();
    await act(async () => { render(<ChoixMedia type="video" testid="v" valeur="/api/files/v1/x.mp4" onChange={() => {}} onOuvrirOutil={ouvrir} />); });
    expect(q('v-actuel').getAttribute('controlslist')).toMatch(/nodownload/);
    await act(async () => { q('v-outil').click(); });
    expect(ouvrir).toHaveBeenCalledWith('/api/files/v1/x.mp4');
    act(() => racine.unmount()); conteneur.remove(); racine = null;
    await act(async () => { render(<ChoixMedia type="audio" testid="a" valeur="/api/files/a1/m.mp3" onChange={() => {}} onOuvrirOutil={ouvrir} />); });
    expect(q('a-outil')).toBeNull();
    expect(q('afroboost-audio-player')).toBeTruthy();
    expect(q('a-actuel').tagName).toBe('AUDIO');
    expect(q('a-actuel').hasAttribute('controls')).toBe(false);
  });

  test('vignette : miniature choisie > carte générée > fond seul', () => {
    expect(sourcesVignette({ image_url: 'https://i/m.jpg', image_source: 'upload', card_url: '/c.jpg' })).toEqual(['https://i/m.jpg', '/c.jpg']);
    expect(sourcesVignette({ image_url: null, image_source: 'default', card_url: '/c.jpg' })).toEqual(['/c.jpg']);
    expect(sourcesVignette({})).toEqual([]);
  });

  test('éditeur : « Capturer depuis la vidéo » ouvre L’OUTIL EXISTANT, la capture devient la miniature (enregistrée)', async () => {
    const EVT = { date: '2026-10-28', heure: '18:45', lieu: 'Valangines', date_modifiable: true, tarifs: null, membres: null, participants: { reservations: 0, paiements: 0 } };
    const INV = { id: 'C1', type: 'event_paid', status: 'draft', title: 'SILENT', image_url: null, image_source: 'default', video_url: '/api/files/v1/silent.mp4', version: 2, card_url: '/api/share/invite/T/carte.jpg?v=2', inviter_display: { prenom: 'Bassi' } };
    axios.get.mockResolvedValue({ data: { invitation: INV, evenement: EVT } });
    axios.put.mockResolvedValue({ data: Object.assign({}, INV, { version: 3 }) });
    uploadToCloudinary.mockResolvedValue({ url: 'https://res.cloudinary.com/dtm0r7hwq/image/upload/v1/invitations/capture.jpg' });
    await act(async () => { render(<EditeurInvitation invitationId="C1" onClose={() => {}} />); });
    await attendre(() => expect(q('ed-titre')).toBeTruthy());
    await act(async () => { q('edit-section-medias-titre').click(); });
    await act(async () => { q('ed-miniature-capturer').click(); });
    await attendre(() => expect(q('outil-existant')).toBeTruthy());
    expect(q('outil-existant').getAttribute('data-url')).toBe('/api/files/v1/silent.mp4');
    await act(async () => { q('outil-capturer').click(); });
    await act(async () => { await new Promise((r) => setTimeout(r, 50)); });
    expect(globalThis.__errCapture || 'aucune erreur').toBe('aucune erreur');
    await attendre(() => expect(axios.put).toHaveBeenCalled());
    const [url, corps] = axios.put.mock.calls[0];
    expect(url).toMatch(/\/api\/referral\/campaigns\/C1$/);
    expect(corps).toEqual({ image_url: 'https://res.cloudinary.com/dtm0r7hwq/image/upload/v1/invitations/capture.jpg', image_source: 'upload' });
    await attendre(() => expect(q('ed-message-retour').textContent).toMatch(/Miniature capturée/));
  });
});

describe('V610g — vidéo publique', () => {
  test('lecture / pause / plein écran / son, mais aucun « Télécharger » ni menu contextuel', async () => {
    await act(async () => { render(<InvitationPublique apercu={{ type: 'event_paid', title: 'SILENT', video_url: '/api/files/v1/silent.mp4', image_url: 'https://i/p.jpg', inviter_display: {} }} token="apercu" />); });
    const v = q('inv-pub-video');
    expect(v.getAttribute('controlslist')).toBe('nodownload noremoteplayback');
    expect(v.hasAttribute('controls')).toBe(true);
    expect(v.autoplay).toBe(false);
    expect(v.getAttribute('poster')).toBe('https://i/p.jpg');
    const ev = new MouseEvent('contextmenu', { bubbles: true, cancelable: true });
    v.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(true);
  });
});

describe('V610k — aperçu « Voir » : plus jamais un cadre noir', () => {
  test('instant d\'aperçu : une vraie image (15 %, entre 1,5 s et la fin)', () => {
    expect(instantApercu(21.2)).toBeCloseTo(3.18, 2);
    expect(instantApercu(6)).toBe(1.5);
    expect(instantApercu(1)).toBeCloseTo(0.9, 5);
    expect(instantApercu(NaN)).toBe(0);
  });
  test('métadonnées chargées, placé sur une vraie image, la lecture repart du DÉBUT, cadre au ratio réel', async () => {
    await act(async () => { render(<ChoixMedia type="video" testid="v" valeur="/api/files/v1/x.mp4" onChange={() => {}} />); });
    const v = q('v-actuel');
    expect(v.getAttribute('preload')).toBe('metadata');           // avant : « none » -> rien chargé, cadre noir
    expect(v.style.width).toBe('auto'); expect(v.style.height).toBe('auto');
    Object.defineProperty(v, 'duration', { configurable: true, get: () => 20 });
    await act(async () => { v.dispatchEvent(new Event('loadedmetadata')); });
    expect(v.currentTime).toBe(3);                                // 15 % de 20 s : une vraie image (pas le fondu noir)
    await act(async () => { v.dispatchEvent(new Event('play')); });
    expect(v.currentTime).toBe(0);                                // la lecture repart du début
  });
});

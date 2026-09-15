/**
 * MODIFIER L'OFFRE > MÉDIAS — la prévisualisation reflète le rendu visiteur,
 * la miniature dédiée est éditable et RELUE, le format vidéo est respecté, et
 * « Afficher Mobile Money » est un choix par offre.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import OfferWizard from '../OfferWizard';

jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), put: jest.fn() } }));
const envois = [];
jest.mock('../../CloudinaryUploadButton', () => ({
  __esModule: true,
  default: () => null,
  uploadToCloudinary: async (f) => { envois.push(f); return { url: '/api/files/mini/image_mini.jpg' }; },
}));
beforeEach(() => {
  HTMLCanvasElement.prototype.getContext = () => ({ drawImage: () => {} });
  HTMLCanvasElement.prototype.toBlob = function (cb) { cb(new Blob(['jpg'], { type: 'image/jpeg' })); };
  window.URL.createObjectURL = jest.fn(() => 'blob:capture'); URL.createObjectURL = window.URL.createObjectURL;
  window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
});

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;
const COACH = 'contact.artboost@gmail.com';

let conteneur, racine, sauvegardee;

async function monter(offre) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  sauvegardee = null;
  await act(async () => {
    racine.render(
      <OfferWizard open isEditing initialOffer={offre} courses={[]} coachEmail={COACH} isSuperAdmin={false} API="/api"
        onSave={(o) => { sauvegardee = o; }} onCancel={() => {}} />
    );
  });
}
async function demonter() {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
}
afterEach(demonter);

async function bouton(regex) {
  const b = [...conteneur.querySelectorAll('button')].find((x) => regex.test((x.textContent || '').trim()));
  if (!b) throw new Error('bouton introuvable : ' + regex);
  await act(async () => { b.click(); });
}
async function allerEtape(n) {
  for (let i = 1; i < n; i += 1) await bouton(/^Suivant/i);
}
const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);

// Le cas réel de production : un .png dans le champ « vidéo ».
const FONDATEURS = { id: 'o-fond', name: 'Fondateurs', price: 59, videoUrl: '/api/files/a/image_a.png', thumbnail: '', images: [], video_aspect_ratio: '16:9' };
const SAISON = { id: 'o-s1', name: 'Saison', price: 549, videoUrl: '/api/files/b/video_b.mp4', thumbnail: 'https://x/mini.jpg', images: [], video_aspect_ratio: '9:16', mobile_money_enabled: true };

test('un .png dans le champ vidéo : la preview montre l’IMAGE (plus un <video> vide), pas de sélecteur de format', async () => {
  await monter(FONDATEURS);
  await allerEtape(3);
  const prev = par('wizard-video-preview');
  expect(prev).not.toBeNull();
  expect(prev.getAttribute('data-ratio')).toBe('image');
  expect(prev.querySelector('img').getAttribute('src')).toBe('/api/files/a/image_a.png');
  expect(prev.querySelector('video')).toBeNull();
  expect(par('wizard-video-ratio')).toBeNull();
});

test('vidéo + miniature : preview au format choisi (9:16, contain), miniature en poster, miniature relue dans le champ', async () => {
  await monter(SAISON);
  await allerEtape(3);
  expect(par('wizard-thumbnail').value).toBe('https://x/mini.jpg');
  expect(par('wizard-thumbnail-preview').getAttribute('src')).toBe('https://x/mini.jpg');
  const prev = par('wizard-video-preview');
  expect(prev.getAttribute('data-ratio')).toBe('9:16');
  expect(par('video-trim-editor')).not.toBeNull();            // l'éditeur partagé
  const v = prev.querySelector('video');
  expect(v.getAttribute('poster')).toBe('https://x/mini.jpg');
  expect(v.style.objectFit).toBe('contain');
  expect(v.style.aspectRatio).toBe('9 / 16');
  expect(par('vte-miniature-apercu').getAttribute('src')).toBe('https://x/mini.jpg');
  // Changer le format met la preview à jour immédiatement.
  await act(async () => { par('video-ratio-1:1').querySelector('input').click(); });
  expect(par('wizard-video-preview').getAttribute('data-ratio')).toBe('1:1');
  expect(par('wizard-video-preview').querySelector('video').style.aspectRatio).toBe('1 / 1');
});

test('« Afficher Mobile Money » : Oui / Non par offre, relu et enregistré', async () => {
  await monter(SAISON);
  // Le mode de paiement (et ce réglage) vivent à l'étape 1, avec le prix.
  expect(par('mobile-money-oui').getAttribute('aria-checked')).toBe('true');
  await act(async () => { par('mobile-money-non').click(); });
  expect(par('mobile-money-non').getAttribute('aria-checked')).toBe('true');
  await allerEtape(3);
  await bouton(/^\s*(Enregistrer|Créer l'offre)\s*$/i);
  await act(async () => { await Promise.resolve(); });
  expect(sauvegardee).not.toBeNull();
  expect(sauvegardee.mobile_money_enabled).toBe(false);
  expect(sauvegardee.thumbnail).toBe('https://x/mini.jpg');
  expect(sauvegardee.video_aspect_ratio).toBe('9:16');
});

test('sans drapeau : « Non » par défaut', async () => {
  await monter(FONDATEURS);
  expect(par('mobile-money-non').getAttribute('aria-checked')).toBe('true');
});

// ✂️ DÉCOUPE VIDÉO — début / fin, aperçu réel, capture, réinitialisation, persistance.
async function metadonnees(video, duree) {
  Object.defineProperty(video, 'duration', { configurable: true, get: () => duree });
  Object.defineProperty(video, 'videoWidth', { configurable: true, get: () => 1080 });
  Object.defineProperty(video, 'videoHeight', { configurable: true, get: () => 1920 });
  Object.defineProperty(video, 'readyState', { configurable: true, get: () => 2 });
  video.play = jest.fn(() => { video.dispatchEvent(new Event('play')); return Promise.resolve(); });
  video.pause = jest.fn(() => { video.dispatchEvent(new Event('pause')); });
  await act(async () => { video.dispatchEvent(new Event('loadedmetadata')); });
}
async function glisser(id, valeur) {
  const el = par(id);
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  await act(async () => { setter.call(el, String(valeur)); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); });
}

test('✂️ vidéo de 21 s : extrait 3 → 18 = 15 s ; Lire l’extrait part à 3 s et s’arrête à 18 s ; capture à 7 s → miniature envoyée ; tout enregistré, original intact', async () => {
  await monter({ ...SAISON, thumbnail: '', video_trim_start: null, video_trim_end: null });
  await allerEtape(3);
  expect(par('vte-attente')).not.toBeNull();
  const v = par('wizard-video-preview').querySelector('video');
  await metadonnees(v, 21);
  expect(par('vte-attente')).toBeNull();
  expect(par('vte-total').textContent).toBe('00:21');
  await glisser('vte-start', 3);
  await glisser('vte-end', 18);
  expect(par('vte-debut').textContent).toBe('00:03');
  expect(par('vte-fin').textContent).toBe('00:18');
  expect(par('vte-extrait').textContent).toBe('00:15');
  // Aperçu réel : lecture de l'extrait bornée.
  v.currentTime = 0;
  await act(async () => { par('vte-lire').click(); });
  expect(v.currentTime).toBe(3);
  expect(v.play).toHaveBeenCalledTimes(1);
  v.currentTime = 18; await act(async () => { v.dispatchEvent(new Event('timeupdate')); });
  expect(v.pause).toHaveBeenCalledTimes(1);
  expect(v.currentTime).toBe(3);
  // Capture à 7 s → miniature envoyée au serveur → `thumbnail` = URL serveur.
  await glisser('vte-scrub', 7);
  await act(async () => { par('vte-capturer').click(); await new Promise((r) => setTimeout(r, 40)); });
  expect(envois).toHaveLength(1);
  expect(par('vte-miniature-apercu').getAttribute('src')).toBe('/api/files/mini/image_mini.jpg');
  await bouton(/^\s*(Enregistrer|Créer l'offre)\s*$/i);
  await act(async () => { await Promise.resolve(); });
  expect(sauvegardee.video_trim_start).toBe(3);
  expect(sauvegardee.video_trim_end).toBe(18);
  expect(sauvegardee.thumbnail).toBe('/api/files/mini/image_mini.jpg');
  expect(sauvegardee.videoUrl).toBe('/api/files/b/video_b.mp4');   // l'original n'est pas touché
});

test('✂️ réouverture : découpe 2 → 17 et miniature relues ; « Réinitialiser » retire la découpe (null, null)', async () => {
  await monter({ ...SAISON, video_trim_start: 2, video_trim_end: 17 });
  await allerEtape(3);
  const v = par('wizard-video-preview').querySelector('video');
  await metadonnees(v, 20);
  expect(v.currentTime).toBe(2);                    // la preview se place au début de l'extrait
  expect(par('vte-debut').textContent).toBe('00:02');
  expect(par('vte-fin').textContent).toBe('00:17');
  expect(par('vte-extrait').textContent).toBe('00:15');
  expect(par('vte-miniature-apercu').getAttribute('src')).toBe('https://x/mini.jpg');
  await act(async () => { par('vte-reset').click(); });
  expect(par('vte-extrait').textContent).toBe('00:20');
  await bouton(/^\s*(Enregistrer|Créer l'offre)\s*$/i);
  await act(async () => { await Promise.resolve(); });
  expect(sauvegardee.video_trim_start).toBeNull();
  expect(sauvegardee.video_trim_end).toBeNull();
  expect(sauvegardee.thumbnail).toBe('https://x/mini.jpg');
});

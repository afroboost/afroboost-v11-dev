/**
 * MODIFIER L'OFFRE > MÉDIAS — la prévisualisation reflète le rendu visiteur,
 * la miniature dédiée est éditable et RELUE, le format vidéo est respecté, et
 * « Afficher Mobile Money » est un choix par offre.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import OfferWizard from '../OfferWizard';

jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), put: jest.fn() } }));
jest.mock('../../CloudinaryUploadButton', () => () => null);

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
  const v = prev.querySelector('video');
  expect(v.getAttribute('poster')).toBe('https://x/mini.jpg');
  expect(v.style.objectFit).toBe('contain');
  expect(v.style.aspectRatio).toBe('9 / 16');
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

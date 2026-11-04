/**
 * V645.4k — MODIFIER L'OFFRE > MÉDIAS : la rubrique « Bannière Boutique ».
 *
 * RÉGRESSION COUVERTE : le gate testait `form.id`, or `form` vient de
 * `newOffer`, une liste blanche de champs qui ne porte PAS `id`
 * (CoachDashboard.startEditOffer garde l'identifiant à part, dans
 * `editingOfferId`). `form.id` valait donc TOUJOURS `undefined` et la rubrique
 * était inatteignable pour toute offre, T-shirt compris.
 * Le gate lit désormais la prop `offerId`.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import OfferWizard from '../OfferWizard';

jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn(() => Promise.resolve({ data: {} })), post: jest.fn(), put: jest.fn() } }));
jest.mock('../../CloudinaryUploadButton', () => ({
  __esModule: true,
  default: () => null,
  uploadToCloudinary: async () => ({ url: '/api/files/mini/image_mini.jpg' }),
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

// Identifiant stable de l'offre T-shirt, identique a OfferWizard.js.
const TSHIRT_OFFER_ID = '84b7d8c6-b859-410a-8a09-0d1ee0069404';

let conteneur, racine;

// `initialOffer` reproduit fidelement `newOffer` : une liste blanche SANS `id`.
const TSHIRT_SANS_ID = {
  name: 'T-shirt Afroboost', price: 35, images: [], thumbnail: '',
  videoUrl: '', offer_type: 'product', category: 'tshirt',
};

async function monter(offerId, { isSuperAdmin = false, initialOffer = TSHIRT_SANS_ID } = {}) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => {
    racine.render(
      <OfferWizard
        open
        isEditing
        offerId={offerId}
        initialOffer={initialOffer}
        courses={[]}
        coachEmail={COACH}
        isSuperAdmin={isSuperAdmin}
        API="/api"
        onSave={() => {}}
        onCancel={() => {}}
      />
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
async function allerEtape3() {
  await bouton(/^Suivant/i);
  await bouton(/^Suivant/i);
}
const texteRubrique = () => /Bannière Boutique/i.test(conteneur.textContent || '');

test("étape 3 : la rubrique Bannière Boutique s'affiche pour l'offre T-shirt, bien que `form.id` soit absent", async () => {
  await monter(TSHIRT_OFFER_ID);
  await allerEtape3();
  // Le formulaire ne porte VOLONTAIREMENT pas d'id : c'est la situation reelle.
  expect(TSHIRT_SANS_ID.id).toBeUndefined();
  expect(texteRubrique()).toBe(true);
});

test('étape 3 : aucune rubrique Bannière pour une autre offre', async () => {
  await monter('une-autre-offre-0000');
  await allerEtape3();
  expect(texteRubrique()).toBe(false);
});

test("étape 3 : aucune rubrique Bannière à la création (pas d'offerId)", async () => {
  await monter(undefined);
  await allerEtape3();
  expect(texteRubrique()).toBe(false);
});

// V646 : un seul éditeur, deux rubriques, et le partenaire garde la sienne.
describe('V646 — quelles rubriques pour qui', () => {
  const rubriques = () => ['banniere-boutique-section', 'banniere-page-boutique-section']
    .map((id) => !!conteneur.querySelector(`[data-testid="${id}"]`));
  const PRODUIT = { name: 'Produit partenaire', price: 10, images: [], isProduct: true };

  test('super-admin + T-shirt : accueil ET page Boutique', async () => {
    await monter(TSHIRT_OFFER_ID, { isSuperAdmin: true });
    await bouton(/Medias/);
    expect(rubriques()).toEqual([true, true]);
  });
  test('super-admin + autre offre : aucune', async () => {
    await monter('autre-offre', { isSuperAdmin: true, initialOffer: PRODUIT });
    await bouton(/Medias/);
    expect(rubriques()).toEqual([false, false]);
  });
  test('partenaire + son produit : sa bannière d\'accueil, pas la page Boutique', async () => {
    await monter('autre-offre', { initialOffer: PRODUIT });
    await bouton(/Medias/);
    expect(rubriques()).toEqual([true, false]);
  });
  test('partenaire + offre non produit : aucune', async () => {
    await monter('autre-offre', { initialOffer: { name: 'Cours', price: 10, images: [] } });
    await bouton(/Medias/);
    expect(rubriques()).toEqual([false, false]);
  });
});

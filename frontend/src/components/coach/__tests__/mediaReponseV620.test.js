// V620 — un média (vidéo OU image) joint à une réponse partenaire : bibliothèque Médias
// EXISTANTE, import par l'envoi existant, 1 média max, carte avant l'envoi, fil V619.
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import MediaReponse, {
  elementsBibliotheque, filtrerBibliotheque, referenceMedia, titreMedia, urlSure, dureeLisible,
} from '../prospection/MediaReponse';
import FilConversation from '../FilConversation';
import { uploadToCloudinary } from '../../CloudinaryUploadButton';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), patch: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));
jest.mock('../../CloudinaryUploadButton', () => ({ __esModule: true, uploadToCloudinary: jest.fn() }));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const VIDEO = '/api/files/c39d44275d0049bb/video_c39d44275d0049bb';
const MINI = '/api/files/7f0d8e0842244e56/image_7f0d8e0842244e56';
const MEDIAS = [
  { id: 'orig-1', niche: 'B', format: 'original', statut: 'en_cours', url: '/api/files/aa11/video_aa11', fichier: { nom: 'AFROBOOST_9.mp4', duree: 51.7 } },
  { id: 'exp-1', niche: 'B', format: '16_9', statut: 'a_verifier', url: VIDEO, source_id: 'orig-1', cible: { nom: 'Associations' }, fichier: { nom: 'AFROBOOST_9_ETUDIANTS_16x9.mp4', duree: 51.82 } },
  { id: 'mini-1', niche: 'B', format: 'miniature', statut: 'en_cours', url: MINI, source_id: 'orig-1', fichier: { nom: 'AFROBOOST_9_miniature.jpg' } },
  { id: 'exp-2', niche: 'C', format: '16_9', statut: 'a_verifier', url: '/api/files/bb22/video_bb22', source_id: 'orig-2', fichier: { nom: 'FESTIVAL_16x9.mp4', duree: 49 } },
  { id: 'arch', niche: 'C', format: '16_9', statut: 'archivee', url: '/api/files/cc33/video_cc33' },
];
const NICHES = [{ cle: 'B', nom: 'Étudiants / associations' }, { cle: 'C', nom: 'Festivals' }];

let conteneur = null;
let racine = null;
async function monter(element) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(element); });
  return conteneur;
}
afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) document.body.removeChild(conteneur);
  racine = null; conteneur = null;
  jest.clearAllMocks();
});
const $ = (t) => document.querySelector(`[data-testid="${t}"]`);
const $$ = (t) => Array.from(document.querySelectorAll(`[data-testid="${t}"]`));
const cliquer = async (el) => { await act(async () => { el.click(); }); };

function servirBibliotheque() {
  axios.get.mockImplementation((url) => {
    if (/prospection-medias/.test(url)) return Promise.resolve({ data: { medias: MEDIAS, total: MEDIAS.length } });
    if (/prospection-niches/.test(url)) return Promise.resolve({ data: { niches: NICHES } });
    return Promise.reject(new Error('inattendu ' + url));
  });
}

function Hote({ initial = null, onVal }) {
  const [v, setV] = React.useState(initial);
  return <MediaReponse API="/api" valeur={v} onChange={(m) => { setV(m); if (onVal) onVal(m); }} />;
}

describe('V620 — fonctions pures', () => {
  test('la bibliothèque : archivés exclus, miniature du même original, image = format miniature', () => {
    const el = elementsBibliotheque(MEDIAS, NICHES);
    expect(el.map((e) => e.media_id)).toEqual(['orig-1', 'exp-1', 'mini-1', 'exp-2']);
    const exp = el.find((e) => e.media_id === 'exp-1');
    expect(exp).toMatchObject({ type: 'video', miniature_url: MINI, niche_nom: 'Étudiants / associations', public: 'Associations', duree: 51.82 });
    expect(el.find((e) => e.media_id === 'orig-1').miniature_url).toBe(MINI);
    expect(el.find((e) => e.media_id === 'exp-2').miniature_url).toBeNull();
    expect(el.find((e) => e.media_id === 'mini-1')).toMatchObject({ type: 'image', miniature_url: MINI });
  });
  test('filtres Tous / Vidéos / Images et recherche', () => {
    const el = elementsBibliotheque(MEDIAS, NICHES);
    expect(filtrerBibliotheque(el, 'tous', '')).toHaveLength(4);
    expect(filtrerBibliotheque(el, 'video', '')).toHaveLength(3);
    expect(filtrerBibliotheque(el, 'image', '').map((e) => e.media_id)).toEqual(['mini-1']);
    expect(filtrerBibliotheque(el, 'tous', 'festiv').map((e) => e.media_id)).toEqual(['exp-2']);
    expect(filtrerBibliotheque(el, 'video', 'associations').map((e) => e.media_id)).toEqual(['orig-1', 'exp-1']);
  });
  test('référence envoyée au serveur : un id de bibliothèque, jamais son adresse', () => {
    expect(referenceMedia({ media_id: 'exp-1', url: VIDEO })).toEqual({ media_id: 'exp-1' });
    expect(referenceMedia({ media_id: null, url: VIDEO, miniature_url: MINI, duree: 3, titre: 'x' }))
      .toEqual({ fichier_url: VIDEO, miniature_url: MINI, duree: 3, nom: 'x' });
    expect(referenceMedia(null)).toBeNull();
  });
  test('titre lisible, adresses sûres, durée', () => {
    expect(titreMedia('AFROBOOST_9_ETUDIANTS_16x9.mp4')).toBe('AFROBOOST 9 ETUDIANTS 16x9');
    expect(urlSure('javascript:alert(1)')).toBe('');
    expect(urlSure('https://x.test/a"b')).toBe('');
    expect(urlSure(VIDEO)).toBe(VIDEO);
    expect(dureeLisible(51.82)).toBe('0:52');
  });
});

describe('V620 — bouton, bibliothèque, choix, retirer, changer', () => {
  test('A/B/C : bouton visible → bibliothèque (vidéos existantes) → carte avec miniature', async () => {
    servirBibliotheque();
    const valeurs = [];
    await monter(<Hote onVal={(m) => valeurs.push(m)} />);
    expect($('ajouter-media').textContent).toMatch(/Ajouter un média/);
    expect($('ajouter-media').querySelector('svg')).not.toBeNull();   // icône SVG, pas d'emoji
    await cliquer($('ajouter-media'));
    expect($('media-fenetre')).not.toBeNull();
    expect($('media-onglet-bibliotheque').getAttribute('aria-selected')).toBe('true');
    expect($('media-onglet-importer')).not.toBeNull();
    expect($$('media-element')).toHaveLength(4);
    await cliquer($('media-filtre-video'));
    expect($$('media-element').every((e) => e.getAttribute('data-type') === 'video')).toBe(true);
    await cliquer($('media-filtre-image'));
    expect($$('media-element')).toHaveLength(1);
    await cliquer($('media-filtre-tous'));
    const exp1 = $$('media-element')[1];
    expect(exp1.querySelector('img').getAttribute('src')).toBe(MINI);
    await cliquer(exp1.querySelector('[data-testid="media-choisir"]'));
    expect($('media-fenetre')).toBeNull();
    expect($('media-joint').getAttribute('data-type')).toBe('video');
    expect($('media-joint').textContent).toMatch(/VIDÉO JOINTE/);
    expect($('media-joint-titre').textContent).toMatch(/AFROBOOST 9 ETUDIANTS 16x9/);
    expect($('media-joint').querySelector('img').getAttribute('src')).toBe(MINI);
    // V625 : plusieurs fichiers — « Ajouter un média » devient « Ajouter un autre fichier ».
    expect($('ajouter-media')).toBeNull();
    expect($('ajouter-autre-fichier').textContent).toMatch(/Ajouter un autre fichier/);
    expect(valeurs[0]).toHaveLength(1);
    expect(valeurs[0][0]).toMatchObject({ media_id: 'exp-1', type: 'video' });
  });

  test('D : Retirer supprime le média (le parent garde son texte)', async () => {
    servirBibliotheque();
    const valeurs = [];
    await monter(<Hote initial={{ media_id: 'exp-1', type: 'video', url: VIDEO, miniature_url: MINI, titre: 'Démo' }}
                      onVal={(m) => valeurs.push(m)} />);
    await cliquer($('media-retirer'));
    expect(valeurs).toEqual([[]]);   // V625 : une liste vide, jamais null
    expect($('media-joint')).toBeNull();
    expect($('ajouter-media')).not.toBeNull();
  });

  test('E (V625) : « Ajouter un autre fichier » → deux médias, chacun retirable', async () => {
    servirBibliotheque();
    await monter(<Hote initial={{ media_id: 'exp-1', type: 'video', url: VIDEO, miniature_url: MINI, titre: 'Démo' }} />);
    await cliquer($('ajouter-autre-fichier'));
    const exp2 = $$('media-element').find((e) => /FESTIVAL/.test(e.textContent));
    await cliquer(exp2.querySelector('[data-testid="media-choisir"]'));
    expect($$('media-joint')).toHaveLength(2);
    expect($$('media-joint-titre')[1].textContent).toMatch(/FESTIVAL 16x9/);
    await cliquer($$('media-retirer')[0]);
    expect($$('media-joint')).toHaveLength(1);
    expect($('media-joint-titre').textContent).toMatch(/FESTIVAL 16x9/);
  });

  test('une image se choisit aussi (IMAGE JOINTE)', async () => {
    servirBibliotheque();
    await monter(<Hote />);
    await cliquer($('ajouter-media'));
    await cliquer($('media-filtre-image'));
    await cliquer($('media-choisir'));
    expect($('media-joint').textContent).toMatch(/IMAGE JOINTE/);
  });

  test("Importer réutilise l'envoi existant (uploadToCloudinary), aucune autre route", async () => {
    servirBibliotheque();
    uploadToCloudinary.mockResolvedValue({ url: '/api/files/dd44/image_dd44' });
    await monter(<Hote />);
    await cliquer($('ajouter-media'));
    await cliquer($('media-onglet-importer'));
    expect($('media-importer-video').textContent).toMatch(/Importer une vidéo/);
    const champ = $('media-fichier');
    expect(champ.getAttribute('accept')).toMatch(/video\/mp4/);
    const f = new File(['x'], 'photo.jpg', { type: 'image/jpeg' });
    Object.defineProperty(champ, 'files', { value: [f], configurable: true });
    await act(async () => { champ.dispatchEvent(new Event('change', { bubbles: true })); });
    expect(uploadToCloudinary).toHaveBeenCalledTimes(1);
    expect(axios.post).not.toHaveBeenCalled();
    expect($('media-joint').textContent).toMatch(/IMAGE JOINTE/);
  });

  test('un fichier non pris en charge est refusé sans envoi', async () => {
    servirBibliotheque();
    await monter(<Hote />);
    await cliquer($('ajouter-media'));
    await cliquer($('media-onglet-importer'));
    const champ = $('media-fichier');
    // V625 : le PDF est désormais accepté ; un fichier texte reste refusé.
    Object.defineProperty(champ, 'files', { value: [new File(['x'], 'a.txt', { type: 'text/plain' })], configurable: true });
    await act(async () => { champ.dispatchEvent(new Event('change', { bubbles: true })); });
    expect(uploadToCloudinary).not.toHaveBeenCalled();
    expect($('media-import-erreur').textContent).toMatch(/MP4/);
  });

  test("aucune couleur de marque codée en dur (var(--primary-color) seulement)", () => {
    const src = require('fs').readFileSync(require('path').join(__dirname, '../prospection/MediaReponse.js'), 'utf8');
    const hex = src.match(/#[0-9a-fA-F]{6}\b/g) || [];
    hex.forEach((h) => expect(src).toMatch(new RegExp(`var\\(--primary-color, ${h}\\)`)));
  });
});

describe('V620 — fil V619 : le média envoyé avec le message', () => {
  test('G : « VIDÉO ENVOYÉE » + miniature + titre + Voir la vidéo', async () => {
    await monter(<FilConversation fil={[
      { id: 't1', direction: 'outgoing', type: 'manual_reply', date: '2026-10-14T14:27:00+00:00', remise: 'remis',
        text: 'Bonjour Madame...', texte_garanti: true,
        media: { type: 'video', titre: 'Afroboost — démonstration', url: VIDEO, miniature_url: MINI } },
      { id: 't2', direction: 'outgoing', type: 'manual_reply', date: '2026-10-14T15:00:00+00:00', remise: 'remis',
        text: 'Sans média', texte_garanti: true, media: null },
    ]} />);
    const m = $$('fil-media');
    expect(m).toHaveLength(1);
    expect(m[0].textContent).toMatch(/VIDÉO ENVOYÉE/);
    expect(m[0].textContent).toMatch(/Afroboost — démonstration/);
    expect(m[0].querySelector('img').getAttribute('src')).toBe(MINI);
    const lien = $('fil-media-voir');
    expect(lien.getAttribute('href')).toBe(VIDEO);
    expect(lien.getAttribute('target')).toBe('_blank');
    expect(lien.getAttribute('rel')).toMatch(/noopener/);
    expect($$('fil-texte')[0].textContent).toBe('Bonjour Madame...');
  });
  test('une adresse piégée ne produit aucun lien', async () => {
    await monter(<FilConversation fil={[{ id: 't', direction: 'outgoing', type: 'manual_reply', text: 'x',
      media: { type: 'video', titre: 'x', url: 'javascript:alert(1)' } }]} />);
    expect($('fil-media')).toBeNull();
  });
});

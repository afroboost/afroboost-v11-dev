/**
 * V646 — PAGE /boutique ET ÉDITEUR UNIQUE DES DEUX BANNIÈRES.
 *
 * Propriétés couvertes :
 *  - les routes sont reconnues sans capter aucune autre URL ;
 *  - l'URL d'un produit survit à son renommage ;
 *  - `?visitor=true` survit à la navigation ;
 *  - l'enregistrement GÉNÉRAL du dashboard n'écrit plus jamais une bannière
 *    (c'était l'écrasement : il réécrivait les valeurs lues à l'ouverture) ;
 *  - l'éditeur, selon sa cible, ne lit et n'écrit QUE ses propres champs.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import fs from 'fs';
import path from 'path';

jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn(), put: jest.fn() } }));
jest.mock('../VideoTrimEditor', () => {
  const R = require('react');
  // Stub : le début et la fin de capture, séparés, comme dans le vrai composant.
  const VTE = (props) => R.createElement('div', null,
    R.createElement('button', { 'data-testid': 'vte-debut', onClick: () => props.onCaptureEnCours(true) }, 'debut'),
    R.createElement('button', { 'data-testid': 'vte-fin', onClick: () => {
      props.onThumbnailCapture(new Blob(['x'], { type: 'image/jpeg' }), 'blob:apercu');
      props.onCaptureEnCours(false);
    } }, 'fin'));
  return { __esModule: true, default: VTE };
});
jest.mock('react-easy-crop', () => ({ __esModule: true, default: () => null }));
jest.mock('../CloudinaryUploadButton', () => {
  const R = require('react');
  const Btn = (props) => R.createElement('button', {
    'data-testid': props['data-testid'],
    onClick: () => props.onUpload('/api/files/nouveau/image.jpg', { resourceType: 'image' }),
  }, 'upload');
  return { __esModule: true, default: Btn, uploadToCloudinary: jest.fn() };
});

import axios from 'axios';
import BanniereBoutiqueSection from '../dashboard/BanniereBoutiqueSection';
import { uploadToCloudinary } from '../CloudinaryUploadButton';
import { lireRouteBoutique, cheminProduit, trouverProduit, avecModeVisiteur } from '../../utils/boutiqueRoute';
import { conceptSansBannieres } from '../../utils/banniereChamps';

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const TSHIRT = { id: '84b7d8c6-b859-410a-8a09-0d1ee0069404', name: 'T-shirt + 1 cours offert!' };

describe('routes de la boutique', () => {
  test('reconnaît la liste et le produit', () => {
    expect(lireRouteBoutique('/boutique')).toBe('');
    expect(lireRouteBoutique('/boutique/')).toBe('');
    expect(lireRouteBoutique('/boutique/t-shirt-84b7d8c6')).toBe('t-shirt-84b7d8c6');
  });

  test.each(['/', '/boutiques', '/boutique/a/b', '/espace/AFR-1', '/coach/boutique', '/parrainage'])(
    'ne capte pas %s', (chemin) => { expect(lireRouteBoutique(chemin)).toBeNull(); });

  test('un segment mal encodé ne fait pas planter la page', () => {
    expect(lireRouteBoutique('/boutique/%E0%A4%A')).toBe('%E0%A4%A');
  });

  test("l'URL du T-shirt est lisible", () => {
    expect(cheminProduit(TSHIRT)).toBe('/boutique/t-shirt-1-cours-offert-84b7d8c6');
  });

  test('un lien déjà partagé survit au renommage du produit', () => {
    const lien = lireRouteBoutique(cheminProduit(TSHIRT));
    expect(trouverProduit([{ ...TSHIRT, name: 'Nouveau nom' }], lien).id).toBe(TSHIRT.id);
  });

  test('un produit inconnu ne renvoie rien', () => {
    expect(trouverProduit([TSHIRT], 'chaussettes-00000000')).toBeNull();
    expect(trouverProduit([TSHIRT], '')).toBeNull();
  });

  test('le mode visiteur survit à la navigation', () => {
    expect(avecModeVisiteur('/boutique', '?visitor=true')).toBe('/boutique?visitor=true');
    expect(avecModeVisiteur('/', '?visitor=true&a=1')).toBe('/?visitor=true');
    expect(avecModeVisiteur('/boutique', '')).toBe('/boutique');
  });
});

describe("l'enregistrement général n'écrit plus les bannières", () => {
  test('retire les champs des deux bannières et garde tout le reste', () => {
    expect(conceptSansBannieres({
      logoUrl: 'l.png',
      primaryColor: '#000',
      home_shop_banner_url: 'ancien',
      home_shop_banner_crop: { x: 0 },
      boutique_page_banner_url: 'ancien',
      boutique_page_banner_trim_end: 4,
    })).toEqual({ logoUrl: 'l.png', primaryColor: '#000' });
  });

  const lire = (rel) => fs.readFileSync(path.join(__dirname, '..', rel), 'utf8');

  test('les deux PUT du tableau de bord passent par ce filtre', () => {
    const src = lire('CoachDashboard.js');
    expect(src.match(/axios\.put\(`\$\{API\}\/concept`, conceptSansBannieres\(concept\)/g)).toHaveLength(2);
    expect(src).not.toMatch(/axios\.put\(`\$\{API\}\/concept`, concept,/);
  });

  test("ConceptEditor existe toujours mais ne touche plus aucune bannière", () => {
    const src = lire('dashboard/ConceptEditor.js');
    expect(src).not.toMatch(/home_shop_banner_(url|type)\s*:/);
    expect(src).not.toMatch(/concept\.home_shop_banner/);
    expect(src).not.toMatch(/boutique_page_banner/);
    expect(src).toMatch(/banniere-boutique-renvoi/);
  });
});

describe('un seul éditeur, deux bannières indépendantes', () => {
  const CONCEPT = {
    home_shop_banner_url: '/api/files/accueil.jpg', home_shop_banner_type: 'image',
    home_shop_banner_crop: { x: 0.1, y: 0.2, zoom: 2 },
    boutique_page_banner_url: '/api/files/page.jpg', boutique_page_banner_type: 'image',
    boutique_page_banner_crop: { x: 0.9, y: 0.8, zoom: 1.5 },
  };
  let conteneur; let racine;

  async function monter(cible) {
    axios.get.mockResolvedValue({ data: CONCEPT });
    axios.put.mockResolvedValue({ data: {} });
    conteneur = document.createElement('div');
    document.body.appendChild(conteneur);
    racine = createRoot(conteneur);
    await act(async () => { racine.render(<BanniereBoutiqueSection API="/api" cible={cible} />); });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  }
  const clic = (id) => act(async () => {
    conteneur.querySelector(`[data-testid="${id}"]`).dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await Promise.resolve();
  });
  const cles = () => Object.keys(axios.put.mock.calls[0][1]);

  afterEach(() => { act(() => racine.unmount()); conteneur.remove(); jest.clearAllMocks(); });

  test('sans cible : la bannière de l\'accueil, testid inchangés', async () => {
    await monter(undefined);
    expect(conteneur.querySelector('[data-testid="banniere-boutique-apercu-img"]').getAttribute('src')).toBe('/api/files/accueil.jpg');
  });

  test('cible boutique : lit SES champs', async () => {
    await monter('boutique');
    expect(conteneur.querySelector('[data-testid="banniere-page-boutique-apercu-img"]').getAttribute('src')).toBe('/api/files/page.jpg');
    expect(conteneur.querySelector('[data-testid="banniere-page-boutique-cadrage-resume"]').textContent).toContain('×1.50');
  });

  test.each([['accueil', 'banniere-boutique', 'boutique_page_banner', 'home_shop_banner'],
    ['boutique', 'banniere-page-boutique', 'home_shop_banner', 'boutique_page_banner']])(
    'cible %s : enregistrer n\'écrit jamais les champs de l\'autre', async (cible, tid, autre, sienne) => {
      await monter(cible);
      await clic(`${tid}-upload`);
      await clic(`${tid}-enregistrer`);
      expect(axios.put).toHaveBeenCalledTimes(1);
      expect(cles().some((k) => k.startsWith(autre))).toBe(false);
      expect(axios.put.mock.calls[0][1][`${sienne}_url`]).toBe('/api/files/nouveau/image.jpg');
    },
  );

  test.each([['accueil', 'banniere-boutique', 'boutique_page_banner'],
    ['boutique', 'banniere-page-boutique', 'home_shop_banner']])(
    'cible %s : retirer n\'efface pas l\'autre', async (cible, tid, autre) => {
      await monter(cible);
      await clic(`${tid}-retirer`);
      expect(cles().some((k) => k.startsWith(autre))).toBe(false);
    },
  );

  test('restaurer le média précédent, repris de l\'ancien éditeur', async () => {
    await monter('boutique');
    await clic('banniere-page-boutique-upload');
    expect(conteneur.querySelector('[data-testid="banniere-page-boutique-apercu-img"]').getAttribute('src')).toBe('/api/files/nouveau/image.jpg');
    await clic('banniere-page-boutique-restaurer');
    expect(conteneur.querySelector('[data-testid="banniere-page-boutique-apercu-img"]').getAttribute('src')).toBe('/api/files/page.jpg');
    expect(conteneur.querySelector('[data-testid="banniere-page-boutique-cadrage-resume"]').textContent).toContain('×1.50');
  });
});

describe.each([['accueil', 'banniere-boutique', 'home_shop_banner', 'boutique_page_banner'],
  ['boutique', 'banniere-page-boutique', 'boutique_page_banner', 'home_shop_banner']])(
  'miniature vidéo, cible %s', (cible, tid, sienne, autre) => {
    let conteneur; let racine;
    const el = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
    const clic = (id) => act(async () => { el(id).dispatchEvent(new MouseEvent('click', { bubbles: true })); await Promise.resolve(); await Promise.resolve(); });

    beforeEach(async () => {
      axios.get.mockResolvedValue({ data: {
        [`${sienne}_url`]: '/api/files/v.mp4', [`${sienne}_type`]: 'video', [`${sienne}_thumbnail`]: '/api/files/ancienne.jpg',
      } });
      axios.put.mockResolvedValue({ data: {} });
      conteneur = document.createElement('div');
      document.body.appendChild(conteneur);
      racine = createRoot(conteneur);
      await act(async () => { racine.render(<BanniereBoutiqueSection API="/api" cible={cible} />); });
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    });
    afterEach(() => { act(() => racine.unmount()); conteneur.remove(); jest.clearAllMocks(); });

    test('dès le clic et jusqu\'à la fin de l\'envoi : bouton bloqué, indicateur, aucun enregistrement', async () => {
      let fin;
      uploadToCloudinary.mockImplementationOnce(() => new Promise((res) => { fin = res; }));
      await clic('vte-debut');
      expect(el(`${tid}-enregistrer`).disabled).toBe(true);
      expect(el(`${tid}-mini-envoi`).textContent).toContain('Enregistrement de la miniature...');
      await clic('vte-fin');
      expect(el(`${tid}-enregistrer`).disabled).toBe(true);
      await clic(`${tid}-enregistrer`);
      expect(axios.put).not.toHaveBeenCalled();
      await act(async () => { fin({ url: '/api/files/nouvelle.jpg' }); await Promise.resolve(); await Promise.resolve(); });
      expect(el(`${tid}-mini-envoi`)).toBeNull();
      expect(el(`${tid}-enregistrer`).disabled).toBe(false);
      await clic(`${tid}-enregistrer`);
      const corps = axios.put.mock.calls[0][1];
      expect(corps[`${sienne}_thumbnail`]).toBe('/api/files/nouvelle.jpg');
      expect(Object.keys(corps).some((k) => k.startsWith(autre))).toBe(false);
    });

    test('échec : erreur claire, ancienne miniature conservée, nouvel essai possible', async () => {
      uploadToCloudinary.mockRejectedValueOnce(new Error('réseau'));
      await clic('vte-debut');
      await clic('vte-fin');
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      expect(el(`${tid}-mini-erreur`).textContent).toMatch(/a échoué.*conservée.*Réessayez/);
      await clic(`${tid}-enregistrer`);
      expect(axios.put.mock.calls[0][1][`${sienne}_thumbnail`]).toBe('/api/files/ancienne.jpg');
      axios.put.mockClear();
      uploadToCloudinary.mockResolvedValueOnce({ url: '/api/files/second-essai.jpg' });
      await clic('vte-debut');
      expect(el(`${tid}-mini-erreur`)).toBeNull();
      await clic('vte-fin');
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      expect(el(`${tid}-mini-erreur`)).toBeNull();
      await clic(`${tid}-enregistrer`);
      expect(axios.put.mock.calls[0][1][`${sienne}_thumbnail`]).toBe('/api/files/second-essai.jpg');
    });

    test('un nouveau média n\'hérite pas d\'une miniature arrivée trop tard', async () => {
      let fin;
      uploadToCloudinary.mockImplementationOnce(() => new Promise((res) => { fin = res; }));
      await clic('vte-debut');
      await clic('vte-fin');
      await clic(`${tid}-upload`);
      await act(async () => { fin({ url: '/api/files/trop-tard.jpg' }); await Promise.resolve(); await Promise.resolve(); });
      await clic(`${tid}-enregistrer`);
      const corps = axios.put.mock.calls[0][1];
      expect(corps[`${sienne}_url`]).toBe('/api/files/nouveau/image.jpg');
      expect(corps[`${sienne}_thumbnail`]).toBe('');
    });
  },
);

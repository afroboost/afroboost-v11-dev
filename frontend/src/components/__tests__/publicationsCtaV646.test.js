/**
 * V646 — la carte de l'accueil : « À la une » et UN appel à l'action.
 * Le fil de la page d'accueil est `PublicationsCarousel` en disposition « fil ».
 */
import fs from 'fs';
import path from 'path';
import React from 'react';

/* `axios` est publié en ESM : comme dans les autres tests de ce dépôt, on le
   remplace. Ce test ne fait AUCUN appel réseau — il ne regarde que le rendu. */
jest.mock('axios', () => ({
  __esModule: true,
  default: {
    get: jest.fn(() => Promise.resolve({ data: [] })),
    post: jest.fn(), put: jest.fn(), patch: jest.fn(), delete: jest.fn(),
  },
}));

import { createRoot } from 'react-dom/client';
import { PublicationsCarousel } from '../Publications';
import { OBJECTIFS, CTAS } from '../../utils/publicationsConversion';

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const pub = (id, sur) => Object.assign({
  id, media_type: 'image', media_url: `https://res.cloudinary.com/x/${id}.jpg`,
  caption: `Légende ${id}`, display_name: 'Coach Bassi', author_id: 'coach@x.ch', coach_id: 'coach@x.ch',
  created_at: '2026-11-09T10:00:00+00:00', remaining_hours: 40,
}, sur || {});

const ACTIONS = () => ({
  likesCount: 3, liked: false, onLike: jest.fn(), commentsCount: 1, onComments: jest.fn(),
  onReserve: jest.fn(), onSessions: jest.fn(), onBoutique: jest.fn(), onLive: jest.fn(),
});

let conteneur; let racine;
const tous = (id) => Array.from(conteneur.querySelectorAll(`[data-testid="${id}"]`));

async function monter(publications, actions) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => {
    racine.render(<PublicationsCarousel publications={publications} actions={actions} disposition="fil" />);
  });
}

afterEach(async () => {
  if (racine) await act(async () => racine.unmount());
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
});

test('sans réglage de conversion, la carte est EXACTEMENT celle d’avant V646', async () => {
  await monter([pub('p1')], ACTIONS());
  expect(tous('publication-fil-carte')).toHaveLength(1);
  expect(tous('publication-cta')).toHaveLength(0);
  expect(tous('publication-a-la-une')).toHaveLength(0);
});

test('un CTA posé affiche UN bouton, qui déclenche la bonne destination', async () => {
  const actions = ACTIONS();
  await monter([pub('p1', { cta: 'boutique' })], actions);
  const boutons = tous('publication-cta');
  expect(boutons).toHaveLength(1);
  expect(boutons[0].getAttribute('data-cta')).toBe('boutique');
  expect(boutons[0].textContent).toContain('Découvrir la boutique');
  await act(async () => { boutons[0].click(); });
  expect(actions.onBoutique).toHaveBeenCalledTimes(1);
  /* Le clic sur le bouton ne doit PAS ouvrir la publication en grand. */
  expect(document.body.querySelector('[data-testid="publication-lightbox"]')).toBeNull();
});

test('le CTA « live » passe par l’entrée Live, pas par les offres', async () => {
  const actions = ACTIONS();
  await monter([pub('p1', { cta: 'live' })], actions);
  await act(async () => { tous('publication-cta')[0].click(); });
  expect(actions.onLive).toHaveBeenCalledTimes(1);
  expect(actions.onReserve).not.toHaveBeenCalled();
});

test('« à la une » pose la pastille, et seulement sur la publication marquée', async () => {
  await monter([pub('p1', { a_la_une: true }), pub('p2')], ACTIONS());
  const marquees = tous('publication-a-la-une');
  expect(marquees).toHaveLength(1);
  expect(marquees[0].closest('[data-testid="publication-fil-carte"]').textContent).toContain('Légende p1');
});

test('un CTA inconnu n’affiche aucun bouton', async () => {
  await monter([pub('p1', { cta: 'teleportation' })], ACTIONS());
  expect(tous('publication-cta')).toHaveLength(0);
});

test('aucun emoji dans les libellés visibles du CTA', async () => {
  await monter([pub('p1', { cta: 'essai' })], ACTIONS());
  expect(tous('publication-cta')[0].textContent).not.toMatch(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u);
});

/* ─── LE MIROIR DES VOCABULAIRES ───
   Le serveur refuse toute valeur hors `V646_OBJECTIFS` / `V646_CTAS`. Si le
   front proposait une valeur de plus, le coach obtiendrait un 400 sans
   comprendre pourquoi ; une valeur de moins et un réglage deviendrait
   inatteignable. Ce test compare les deux listes à la source. */
test('les vocabulaires du front et du serveur sont identiques', () => {
  const serveur = fs.readFileSync(path.join(__dirname, '../../../../api/server.py'), 'utf8');
  const liste = (nom) => {
    const bloc = new RegExp(`${nom}\\s*=\\s*\\(([\\s\\S]*?)\\)`).exec(serveur);
    expect(bloc).toBeTruthy();
    return (bloc[1].match(/"([a-z_]+)"/g) || []).map((x) => x.replace(/"/g, ''));
  };
  expect(liste('V646_OBJECTIFS')).toEqual(OBJECTIFS.map((o) => o.id));
  expect(liste('V646_CTAS')).toEqual(CTAS.map((c) => c.id));
});

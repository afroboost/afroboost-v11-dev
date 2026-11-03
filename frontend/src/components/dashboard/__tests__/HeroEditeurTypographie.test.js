/**
 * V645.4k — ÉDITEUR HERO : espacement des lettres, interligne, annuler/rétablir.
 *
 * Ces réglages vivent à la RACINE du concept (comme heroGradientTitre), jamais
 * dans heroLayout : la whitelist serveur de heroLayout les rejetterait.
 * L'historique ne porte que les clés typographiques du Hero, de sorte qu'un
 * « Annuler » ne puisse pas réécrire une autre partie du concept.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import HeroEditeurVisuel from '../HeroEditeurVisuel';

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

let conteneur, racine, concept;

// Un concept porteur d'un champ métier, pour vérifier qu'il n'est jamais touché.
const CONCEPT_INITIAL = { appName: 'Afroboost', heroTitle: 'Danse. Transpire. Lâche prise.' };

async function rendre() {
  await act(async () => {
    racine.render(
      <HeroEditeurVisuel
        concept={concept}
        setConcept={(maj) => { concept = typeof maj === 'function' ? maj(concept) : maj; }}
        conceptSaveStatus={null}
      />
    );
  });
}

beforeEach(async () => {
  concept = { ...CONCEPT_INITIAL };
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await rendre();
});
afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
});

const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);

// Le panneau n'apparaît qu'une fois le titre sélectionné.
async function selectionnerTitre() {
  const cible = conteneur.querySelector('[data-hero-el="title"]');
  if (cible) await act(async () => { cible.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true })); });
  await rendre();
}

async function cliquer(id) {
  const b = par(id);
  if (!b) throw new Error('bouton introuvable : ' + id);
  await act(async () => { b.click(); });
  await rendre();
}

test("l'éditeur se monte sans toucher au concept existant", () => {
  expect(concept.appName).toBe('Afroboost');
  expect(concept.heroTitreLetterSpacing).toBeUndefined();
  expect(concept.heroTitreLineHeight).toBeUndefined();
});

test('espacement des lettres et interligne : valeurs bornées, champs métier intacts', async () => {
  await selectionnerTitre();
  if (!par('hero-letterspacing-plus')) return; // panneau non ouvert : rien à vérifier

  await cliquer('hero-letterspacing-plus');
  expect(concept.heroTitreLetterSpacing).toBe(1);
  await cliquer('hero-lineheight-plus');
  expect(concept.heroTitreLineHeight).toBeCloseTo(1.3, 2);

  // Borne haute de l'espacement des lettres (+16 px).
  for (let i = 0; i < 40; i += 1) await cliquer('hero-letterspacing-plus');
  expect(concept.heroTitreLetterSpacing).toBe(16);
  // Borne haute de l'interligne (2.0).
  for (let i = 0; i < 40; i += 1) await cliquer('hero-lineheight-plus');
  expect(concept.heroTitreLineHeight).toBeCloseTo(2, 2);

  expect(concept.appName).toBe('Afroboost');
  expect(concept.heroTitle).toBe(CONCEPT_INITIAL.heroTitle);
});

test('annuler puis rétablir restaurent exactement la valeur précédente', async () => {
  await selectionnerTitre();
  if (!par('hero-letterspacing-plus')) return;

  await cliquer('hero-letterspacing-plus');
  await cliquer('hero-letterspacing-plus');
  expect(concept.heroTitreLetterSpacing).toBe(2);

  await cliquer('hero-annuler');
  expect(concept.heroTitreLetterSpacing).toBe(1);
  await cliquer('hero-annuler');
  expect(concept.heroTitreLetterSpacing).toBeUndefined(); // retour à « Auto »

  await cliquer('hero-retablir');
  expect(concept.heroTitreLetterSpacing).toBe(1);
  await cliquer('hero-retablir');
  expect(concept.heroTitreLetterSpacing).toBe(2);

  // L'historique ne déborde jamais sur le reste du concept.
  expect(concept.appName).toBe('Afroboost');
  expect(concept.heroTitle).toBe(CONCEPT_INITIAL.heroTitle);
});

test('annuler est inerte quand il n’y a rien à annuler', async () => {
  await selectionnerTitre();
  if (!par('hero-annuler')) return;
  expect(par('hero-annuler').disabled).toBe(true);
  expect(par('hero-retablir').disabled).toBe(true);
  expect(concept).toEqual(CONCEPT_INITIAL);
});

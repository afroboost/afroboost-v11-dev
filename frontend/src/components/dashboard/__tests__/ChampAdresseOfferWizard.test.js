/**
 * U1b — LE VRAI WIZARD, LE VRAI GESTE DU COACH.
 *
 * Le lieu se saisit a deux endroits du wizard, et un seul est reellement
 * visible en production : le champ de L'HORAIRE. Le champ « Lieu » de l'offre
 * est masque des qu'un horaire est lie — c'est le cas de 7 offres sur 9 en
 * base. Ce banc pilote donc le composant REEL, sur les deux champs.
 *
 * Ce qu'il refuse de laisser passer :
 *   - une liste de suggestions qui ne s'ouvre pas quand le service repond ;
 *   - un choix qui n'ecrit pas dans le champ ;
 *   - une saisie libre rendue impossible apres un choix ;
 *   - et surtout : un service tiers en panne qui empeche d'enregistrer.
 *
 * Aucune requete ne sort : `fetch` et `axios` sont des mouchards.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import OfferWizard from '../OfferWizard';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn() },
}));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const COACH = 'contact.artboost@gmail.com';

const REPONSE_OSM = [{
  place_id: 1,
  display_name: 'Rue des Vallangines, 97, Neuchâtel, District de Neuchâtel, 2000, Suisse',
  name: 'Rue des Vallangines',
  address: {
    road: 'Rue des Vallangines', house_number: '97', city: 'Neuchâtel',
    postcode: '2000', state: 'Neuchâtel', country: 'Suisse', country_code: 'ch'
  }
}, {
  place_id: 2,
  display_name: 'Avenue de Vidy, Lausanne, 1007, Suisse',
  name: 'Avenue de Vidy',
  address: {
    road: 'Avenue de Vidy', city: 'Lausanne', postcode: '1007',
    state: 'Vaud', country: 'Suisse', country_code: 'ch'
  }
}];

const ADRESSE_1 = 'Rue des Vallangines 97, 2000 Neuchâtel';

// L'etat REEL de production : un horaire recurrent, avec un lieu mal saisi
// (espace en tete) qu'on ne doit surtout PAS reecrire tout seul.
const LUNDI = {
  id: 'c-lundi', name: 'Silent lundi', weekday: 1, date: '', time: '18:30',
  locationName: ' Plage Est de St-Blaise - La Torpille', coach_id: COACH, visible: true
};

const OFFRE_AVEC_HORAIRE = {
  id: 'offre-silent', name: 'SILENT LAKESIDE', price: 25,
  location: ' Plage Est de St-Blaise - La Torpille',
  linked_course_ids: [LUNDI.id],
};

// Une offre d'avant ce lot, SANS aucun lieu : elle doit s'ouvrir sans erreur.
const OFFRE_SANS_LIEU = { id: 'offre-produit', name: 'T-shirt', price: 40, isProduct: true };

let conteneur, racine, sauvegardee;

function servirOSM(donnees = REPONSE_OSM) {
  global.fetch = jest.fn(() => Promise.resolve({
    ok: true, json: () => Promise.resolve(donnees)
  }));
}

function serviceEnPanne() {
  global.fetch = jest.fn(() => Promise.reject(new TypeError('Failed to fetch')));
}

async function monter(courses, offre) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  sauvegardee = null;
  await act(async () => {
    racine.render(
      <OfferWizard
        open
        isEditing
        initialOffer={offre}
        courses={courses}
        coachEmail={COACH}
        isSuperAdmin={false}
        API="/api"
        onSave={(o) => { sauvegardee = o; }}
        onCancel={() => {}}
      />
    );
  });
  await allerEtape2();
}

async function allerEtape2() {
  const btn = [...conteneur.querySelectorAll('button')]
    .find(b => (b.textContent || '').trim().includes('Logistique'));
  if (btn) await act(async () => { btn.click(); });
}

async function saisir(el, valeur) {
  const setter = Object.getOwnPropertyDescriptor(
    el.constructor.prototype, 'value').set;
  await act(async () => {
    setter.call(el, valeur);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

/** Laisse passer le debounce ET la reponse du service. */
async function laisserVenirLesSuggestions() {
  await act(async () => { jest.advanceTimersByTime(1600); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
}

async function enregistrer() {
  for (let i = 0; i < 4; i += 1) {
    const suivant = [...conteneur.querySelectorAll('button')]
      .find(b => /Suivant/i.test(b.textContent || ''));
    if (!suivant) break;
    await act(async () => { suivant.click(); });
  }
  const btn = [...conteneur.querySelectorAll('button')]
    .find(b => /^\s*(Enregistrer|Créer l'offre)\s*$/i.test(b.textContent || ''));
  if (!btn) throw new Error('bouton d\'enregistrement introuvable');
  await act(async () => { btn.click(); });
  await act(async () => { await Promise.resolve(); });
  await act(async () => { await Promise.resolve(); });
}

function champHoraire() {
  const el = conteneur.querySelector(`[data-testid="course-location-${LUNDI.id}"]`);
  if (!el) throw new Error('champ lieu de l\'horaire introuvable');
  return el;
}

function panneauHoraire() {
  return conteneur.querySelector(`[data-testid="course-location-${LUNDI.id}-suggestions"]`);
}

function payloadHoraire() {
  const appel = [...axios.put.mock.calls].reverse()
    .find(a => String(a[0]).endsWith(LUNDI.id));
  return appel ? appel[1] : null;
}

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers();
  axios.put.mockResolvedValue({ data: {} });
  axios.post.mockResolvedValue({ data: { id: 'c-neuf' } });
  servirOSM();
});

afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
  jest.useRealTimers();
  delete global.fetch;
});

describe('LE CHAMP REELLEMENT VISIBLE : le lieu de l\'horaire', () => {
  test('l\'adresse deja en base s\'affiche telle quelle — aucune reecriture', async () => {
    await monter([LUNDI], OFFRE_AVEC_HORAIRE);
    // L'espace en tete de « Plage Est... » est CONSERVE : normaliser une
    // adresse existante sans que le coach l'ait demande serait une migration.
    expect(champHoraire().value).toBe(' Plage Est de St-Blaise - La Torpille');
    // Et rien n'est parti au service : ouvrir une offre n'interroge personne.
    await laisserVenirLesSuggestions();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test('taper propose des adresses', async () => {
    await monter([LUNDI], OFFRE_AVEC_HORAIRE);
    expect(panneauHoraire()).toBeNull();
    await saisir(champHoraire(), 'vallangines');
    await laisserVenirLesSuggestions();
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(String(global.fetch.mock.calls[0][0])).toContain('nominatim.openstreetmap.org');
    const panneau = panneauHoraire();
    expect(panneau).toBeTruthy();
    expect(panneau.textContent).toContain(ADRESSE_1);
  });

  test('deux frappes rapides ne font QU\'UNE requete (politique 1 req/s)', async () => {
    await monter([LUNDI], OFFRE_AVEC_HORAIRE);
    await saisir(champHoraire(), 'val');
    await act(async () => { jest.advanceTimersByTime(100); });
    await saisir(champHoraire(), 'vallan');
    await act(async () => { jest.advanceTimersByTime(100); });
    await saisir(champHoraire(), 'vallangines');
    await laisserVenirLesSuggestions();
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  test('sous 3 caracteres, aucune requete', async () => {
    await monter([LUNDI], OFFRE_AVEC_HORAIRE);
    await saisir(champHoraire(), 'ne');
    await laisserVenirLesSuggestions();
    expect(global.fetch).not.toHaveBeenCalled();
    expect(panneauHoraire()).toBeNull();
  });

  test('choisir une proposition remplit le champ et ferme la liste', async () => {
    await monter([LUNDI], OFFRE_AVEC_HORAIRE);
    await saisir(champHoraire(), 'vallangines');
    await laisserVenirLesSuggestions();
    const option = conteneur.querySelector(
      `[data-testid="course-location-${LUNDI.id}-suggestion-0"]`);
    await act(async () => { option.click(); });
    expect(champHoraire().value).toBe(ADRESSE_1);
    expect(panneauHoraire()).toBeNull();
  });

  test('le choix part au serveur dans locationName', async () => {
    await monter([LUNDI], OFFRE_AVEC_HORAIRE);
    await saisir(champHoraire(), 'vallangines');
    await laisserVenirLesSuggestions();
    await act(async () => {
      conteneur.querySelector(`[data-testid="course-location-${LUNDI.id}-suggestion-0"]`).click();
    });
    await enregistrer();
    expect(payloadHoraire()).toMatchObject({ locationName: ADRESSE_1 });
    expect(sauvegardee).toBeTruthy();
  });

  test('APRES un choix, la saisie libre reste possible', async () => {
    await monter([LUNDI], OFFRE_AVEC_HORAIRE);
    await saisir(champHoraire(), 'vallangines');
    await laisserVenirLesSuggestions();
    await act(async () => {
      conteneur.querySelector(`[data-testid="course-location-${LUNDI.id}-suggestion-0"]`).click();
    });
    // Le coach ecrase par un lieu qui n'existe dans AUCUN annuaire.
    await saisir(champHoraire(), 'Salle Afroboost');
    expect(champHoraire().value).toBe('Salle Afroboost');
    await enregistrer();
    expect(payloadHoraire()).toMatchObject({ locationName: 'Salle Afroboost' });
  });

  test('un lieu qui n\'est pas une adresse postale s\'enregistre quand meme', async () => {
    // Le service ne renvoie rien pour ce texte : la liste doit rester fermee
    // et la saisie partir telle quelle.
    global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve([]) }));
    await monter([LUNDI], OFFRE_AVEC_HORAIRE);
    await saisir(champHoraire(), 'Plage Est de St-Blaise - La Torpille');
    await laisserVenirLesSuggestions();
    expect(panneauHoraire()).toBeNull();
    await enregistrer();
    expect(payloadHoraire()).toMatchObject({
      locationName: 'Plage Est de St-Blaise - La Torpille'
    });
  });
});

describe('SERVICE INDISPONIBLE — le wizard doit se comporter comme avant', () => {
  test('aucune liste, aucun message d\'erreur, le texte saisi est intact', async () => {
    serviceEnPanne();
    await monter([LUNDI], OFFRE_AVEC_HORAIRE);
    await saisir(champHoraire(), 'vallangines');
    await laisserVenirLesSuggestions();
    expect(panneauHoraire()).toBeNull();
    expect(champHoraire().value).toBe('vallangines');
    expect(conteneur.textContent).not.toMatch(/erreur|Erreur|indisponible|échec/);
  });

  test('l\'offre s\'enregistre malgre la panne', async () => {
    serviceEnPanne();
    await monter([LUNDI], OFFRE_AVEC_HORAIRE);
    await saisir(champHoraire(), 'Bord du Lac, Auvernier');
    await laisserVenirLesSuggestions();
    await enregistrer();
    expect(sauvegardee).toBeTruthy();
    expect(sauvegardee.name).toBe('SILENT LAKESIDE');
    expect(payloadHoraire()).toMatchObject({ locationName: 'Bord du Lac, Auvernier' });
  });

  test('meme sans fetch du tout (vieux navigateur), le champ reste utilisable', async () => {
    delete global.fetch;
    await monter([LUNDI], OFFRE_AVEC_HORAIRE);
    await saisir(champHoraire(), 'Auvernier');
    await laisserVenirLesSuggestions();
    expect(champHoraire().value).toBe('Auvernier');
    await enregistrer();
    expect(sauvegardee).toBeTruthy();
  });
});

describe('LE CHAMP « Lieu » DE L\'OFFRE (sans horaire lie)', () => {
  test('une offre d\'avant ce lot, sans lieu, s\'ouvre sans erreur', async () => {
    await monter([], OFFRE_SANS_LIEU);
    const champ = conteneur.querySelector('[data-testid="offer-location"]');
    expect(champ).toBeTruthy();
    expect(champ.value).toBe('');
  });

  test('il propose et enregistre l\'adresse choisie dans location', async () => {
    await monter([], OFFRE_SANS_LIEU);
    const champ = conteneur.querySelector('[data-testid="offer-location"]');
    await saisir(champ, 'vallangines');
    await laisserVenirLesSuggestions();
    const option = conteneur.querySelector('[data-testid="offer-location-suggestion-0"]');
    expect(option).toBeTruthy();
    await act(async () => { option.click(); });
    expect(conteneur.querySelector('[data-testid="offer-location"]').value).toBe(ADRESSE_1);
    await enregistrer();
    expect(sauvegardee.location).toBe(ADRESSE_1);
  });
});

describe('LE RESTE DU WIZARD EST INTACT', () => {
  test('les autres champs de l\'etape Logistique repondent toujours', async () => {
    await monter([], OFFRE_SANS_LIEU);
    const duree = conteneur.querySelector('input[placeholder="60"]');
    const participants = conteneur.querySelector('input[placeholder="20"]');
    expect(duree).toBeTruthy();
    expect(participants).toBeTruthy();
    await saisir(duree, '45');
    await saisir(participants, '12');
    await enregistrer();
    expect(sauvegardee).toMatchObject({ duration_minutes: 45, max_participants: 12 });
  });

  test('le nom, le prix et l\'audience traversent le wizard sans changer', async () => {
    await monter([LUNDI], { ...OFFRE_AVEC_HORAIRE, audience: 'women-only' });
    await saisir(champHoraire(), 'vallangines');
    await laisserVenirLesSuggestions();
    await act(async () => {
      conteneur.querySelector(`[data-testid="course-location-${LUNDI.id}-suggestion-0"]`).click();
    });
    await enregistrer();
    expect(sauvegardee).toMatchObject({
      name: 'SILENT LAKESIDE', price: 25, audience: 'women-only'
    });
  });

  test('ouvrir puis enregistrer sans rien toucher n\'envoie AUCUN horaire', async () => {
    await monter([LUNDI], OFFRE_AVEC_HORAIRE);
    await enregistrer();
    expect(axios.put).not.toHaveBeenCalled();
    expect(sauvegardee.linked_course_ids).toEqual([LUNDI.id]);
  });
});

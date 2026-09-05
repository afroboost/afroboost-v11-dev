// R2c — LE TYPE ET LE PROPRIETAIRE, VUS DU NAVIGATEUR.
//
// CE QUI EST PROUVE ICI, ET POURQUOI CHAQUE POINT COMPTE :
//
//   * l'ecran de classification n'existe PAS pour un partenaire — la garde
//     serveur est doublee cote client, pour qu'il ne voie meme pas la porte ;
//   * il ne demande RIEN tant qu'on ne l'ouvre pas : une offre classee est un
//     rattrapage ponctuel, pas une requete a chaque affichage du dashboard ;
//   * classer envoie l'identifiant OPAQUE du partenaire, jamais son e-mail —
//     R2b vient de les retirer des routes publiques, cet ecran ne les y ramene
//     pas par la porte de derriere ;
//   * `owner_type` et `owner_id` ne partent d'AUCUN formulaire d'offre : le
//     proprietaire est un constat serveur, pas un champ de saisie ;
//   * `offer_type`, lui, part bien — et surtout, il est RELU a la reouverture
//     d'une offre. C'est le piege qui a coute sept correctifs a ce depot :
//     un champ envoye mais jamais relu revient a « non classifie » en base a
//     la sauvegarde suivante.
//
// `axios` est mocke : aucun appel reseau ne part de ces tests.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import fs from 'fs';
import path from 'path';
import axios from 'axios';
import OffersClassification from '../OffersClassification';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), patch: jest.fn() }
}));

const LIRE = (p) => fs.readFileSync(path.join(__dirname, p), 'utf8');
const DASHBOARD = LIRE('../../CoachDashboard.js');
const WIZARD = LIRE('../OfferWizard.js');

const REPONSE = {
  data: {
    offres: [{
      id: 'legacy-1', name: 'PULSE x10 cours', visible: false, price: 250,
      linked_course_ids: ['c1'], duration_value: 2, duration_unit: 'months',
      owner_type: 'unknown', owner_id: null, offer_type: 'unknown',
      a_classifier: true
    }],
    total: 1, a_classifier: 1,
    types: [{ valeur: 'pack', libelle: 'Pack' },
            { valeur: 'single_class', libelle: "Cours à l'unité" }],
    proprietaires: [{ valeur: 'admin', libelle: 'Afroboost / Administrateur' },
                    { valeur: 'partner', libelle: 'Coach partenaire' }],
    partenaires: [{ id: 'uuid-du-partenaire', name: 'Partenaire Un', is_active: true }]
  }
};

let conteneur;
let racine;

const monter = (props) => {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  act(() => {
    racine.render(<OffersClassification API="/api" isSuperAdmin coachEmail="admin@x.test" {...props} />);
  });
};

const cliquer = (testid) => {
  const el = conteneur.querySelector(`[data-testid="${testid}"]`);
  if (!el) throw new Error(`introuvable : ${testid}`);
  act(() => { el.dispatchEvent(new MouseEvent('click', { bubbles: true })); });
};

const ouvrir = async () => {
  const bouton = conteneur.querySelector('button');
  await act(async () => {
    bouton.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await Promise.resolve();
  });
};

beforeEach(() => {
  jest.clearAllMocks();
  axios.get.mockResolvedValue(REPONSE);
  axios.patch.mockResolvedValue({ data: { success: true } });
});

afterEach(() => {
  act(() => racine.unmount());
  conteneur.remove();
});

describe("R2c — l'ecran de classification", () => {
  test('un coach partenaire ne le voit PAS du tout', () => {
    monter({ isSuperAdmin: false });
    expect(conteneur.querySelector('[data-testid="r2c-classification"]')).toBeNull();
    expect(axios.get).not.toHaveBeenCalled();
  });

  test("il n'interroge le serveur QU'a l'ouverture", async () => {
    monter({});
    expect(conteneur.querySelector('[data-testid="r2c-classification"]')).not.toBeNull();
    expect(axios.get).not.toHaveBeenCalled();
    await ouvrir();
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(axios.get.mock.calls[0][0]).toBe('/api/offers/classification');
  });

  test("il montre l'offre a classer et ce qu'on sait d'elle", async () => {
    monter({});
    await ouvrir();
    const texte = conteneur.textContent;
    expect(texte).toContain('PULSE x10 cours');
    expect(texte).toContain('250 CHF');
    expect(texte).toContain('masquée');
    // Aucune classification n'est PROPOSEE comme deja faite : les deux
    // questions sont posees vierges.
    expect(conteneur.querySelector('[data-testid="r2c-type-legacy-1-pack"]')).not.toBeNull();
    expect(conteneur.querySelector('[data-testid="r2c-proprio-legacy-1-admin"]')).not.toBeNull();
  });

  test('classer envoie le choix humain — et rien de plus', async () => {
    monter({});
    await ouvrir();
    cliquer('r2c-proprio-legacy-1-admin');
    cliquer('r2c-type-legacy-1-pack');
    await act(async () => {
      conteneur.querySelector('[data-testid="r2c-enregistrer-legacy-1"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }));
      await Promise.resolve();
    });
    expect(axios.patch).toHaveBeenCalledTimes(1);
    const [url, corps] = axios.patch.mock.calls[0];
    expect(url).toBe('/api/offers/legacy-1/classification');
    expect(corps).toEqual({ owner_type: 'admin', partner_id: null, offer_type: 'pack' });
    // Ni prix, ni visibilite, ni cours lies : cet ecran classe, il n'edite pas.
    ['price', 'visible', 'linked_course_ids', 'name', 'duration_value']
      .forEach((champ) => expect(corps).not.toHaveProperty(champ));
  });

  test("un partenaire est designe par son identifiant OPAQUE, jamais par un e-mail", async () => {
    monter({});
    await ouvrir();
    cliquer('r2c-proprio-legacy-1-partner');
    const select = conteneur.querySelector('select');
    expect(select).not.toBeNull();
    const valeurs = Array.from(select.options).map((o) => o.value).filter(Boolean);
    expect(valeurs).toEqual(['uuid-du-partenaire']);
    valeurs.forEach((v) => expect(v).not.toContain('@'));
  });

  test('sans reponse complete, rien ne part', async () => {
    window.alert = jest.fn();
    monter({});
    await ouvrir();
    cliquer('r2c-proprio-legacy-1-admin');   // le type manque
    await act(async () => {
      conteneur.querySelector('[data-testid="r2c-enregistrer-legacy-1"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }));
      await Promise.resolve();
    });
    expect(axios.patch).not.toHaveBeenCalled();
  });
});

// --------------------------------------------------------------------------
describe('R2c — le type dans le formulaire d offre', () => {
  test('les sept types sont proposes, en francais, sans jargon', () => {
    ["Cours à l'unité", 'Événement', 'Abonnement', 'Pack', 'Carte membre',
     'Produit', 'Autre'].forEach((libelle) => {
      expect(WIZARD).toContain(libelle);
    });
    // `unknown` n'est PAS un choix : il est reserve aux offres d'avant ce lot.
    expect(WIZARD).not.toMatch(/valeur:\s*'unknown'/);
  });

  test("le wizard bloque une CREATION sans type, pas une modification", () => {
    expect(WIZARD).toContain('if (!form.offer_type && !isEditing) {');
  });

  test('`offer_type` part bien dans la requete', () => {
    expect(DASHBOARD).toMatch(/offer_type:\s*src\.offer_type/);
  });

  test("... et il est RELU a la reouverture — le piege des sept correctifs", () => {
    // Envoye mais jamais relu, le champ reviendrait a « non classifie » en base
    // a chaque sauvegarde. C'est exactement ce qui est arrive a `audience`.
    expect(DASHBOARD).toMatch(/offer_type:\s*offer\.offer_type/);
  });

  test("une offre NEUVE n'a aucun type pre-choisi", () => {
    // Un defaut « cours a l'unite » serait accepte sans que le coach ait rien
    // lu — et c'est precisement le type qui rendra l'offre publique.
    expect(DASHBOARD).toMatch(/offer_type:\s*''/);
  });

  test('le navigateur n envoie JAMAIS le proprietaire', () => {
    // Le bloc de construction du payload d'offre ne doit porter ni owner_type
    // ni owner_id : le serveur les etablit depuis la session authentifiee.
    const i = DASHBOARD.indexOf('offer_type: src.offer_type');
    const bloc = DASHBOARD.slice(i - 4000, i + 500);
    expect(bloc).not.toMatch(/owner_type:\s*src\./);
    expect(bloc).not.toMatch(/owner_id:\s*src\./);
  });
});

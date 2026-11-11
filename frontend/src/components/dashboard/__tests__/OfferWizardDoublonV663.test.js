/**
 * V663 — LE VRAI WIZARD, ET LE GESTE QUI A CRÉÉ LE DOUBLON.
 *
 * Ce que ce banc reproduit : le coach ouvre l'offre « Cours à l'unité » et
 * clique « Ajouter un horaire ». Avant ce lot, le cours créé prenait LE NOM DE
 * L'OFFRE — c'est ainsi qu'un COURS « Cours à l'unité » est né en double de
 * l'Afroboost Silent réel. Mesuré en production le 11/11/2026 :
 *
 *   mercredi 18:45, Valangines 97 — « Afroboost Silent – Session Cardio » : 71 résa
 *   mercredi 18:45, Valangines 97 — « Cours à l'unité »                   : 13 résa
 *
 * On pilote le composant RÉEL et on lit ce qui part au serveur. Aucune requête
 * ne sort : axios est un mouchard.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import OfferWizard from '../OfferWizard';
import { NOM_PROVISOIRE } from '../../../utils/creneauDoublon';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn() },
}));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const COACH = 'contact.artboost@gmail.com';
const VAL = 'Chemin des Valangines 97, 2000 Neuchâtel';

// Les deux fiches réelles du mercredi 18:45, au même endroit.
const SILENT = {
  id: 'c-silent', name: 'Afroboost Silent – Session Cardio', weekday: 3, date: '',
  time: '18:45', locationName: VAL, coach_id: COACH, visible: true,
};
const DOUBLON = {
  id: 'c-doublon', name: "Cours à l'unité", weekday: 3, date: '',
  time: '18:45', locationName: VAL, coach_id: COACH, visible: true,
};
// Un cours RÉELLEMENT différent, même jour, même heure, AILLEURS.
const AILLEURS = {
  id: 'c-ailleurs', name: 'Afroboost Live', weekday: 3, date: '',
  time: '18:45', locationName: 'ArtDanse, Martigny', coach_id: COACH, visible: true,
};

const NOMS_OFFRES = ["Cours à l'unité", 'PULSE x10 cours', 'Membres', 'Saison hiver — 8 mois'];

let conteneur, racine;

async function monter(courses, lies) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => {
    racine.render(
      <OfferWizard
        open
        isEditing
        initialOffer={{
          id: 'offre-unite', name: "Cours à l'unité", price: 25,
          location: VAL,
          linked_course_ids: lies,
        }}
        courses={courses}
        offerNames={NOMS_OFFRES}
        coachEmail={COACH}
        isSuperAdmin={false}
        API="/api"
        onSave={() => {}}
        onCancel={() => {}}
      />
    );
  });
  // Les horaires vivent à l'étape 2 « Logistique ». On y va PAR LE LIBELLÉ,
  // comme le coach — un sélecteur `data-step` n'existe pas dans ce wizard, et
  // s'y fier rendait un faux « rien à signaler » : le bloc n'était simplement
  // jamais rendu.
  const onglet = Array.from(conteneur.querySelectorAll('button'))
    .find((b) => (b.textContent || '').includes('Logistique'));
  if (!onglet) throw new Error("onglet « Logistique » introuvable");
  await act(async () => { onglet.click(); });
}

afterEach(async () => {
  if (racine) await act(async () => racine.unmount());
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
  jest.clearAllMocks();
});

describe('V663 — une offre ne donne plus son nom à une séance', () => {
  test('« Ajouter un horaire » n’envoie PLUS le nom de l’offre', async () => {
    axios.post.mockResolvedValue({ data: { id: 'c-neuf', name: NOM_PROVISOIRE, weekday: 3, time: '18:30' } });
    await monter([SILENT], [SILENT.id]);

    const bouton = Array.from(conteneur.querySelectorAll('button'))
      .find((b) => /ajouter un horaire|ajouter un cours|nouvel horaire/i.test(b.textContent || ''));
    // AUCUNE PORTE DE SORTIE. J'en avais écrit une (« si le bouton est
    // introuvable, on passe quand même ») : c'est exactement le faux PASS que
    // ce projet m'interdit. Si le geste du coach n'est pas reproductible, le
    // banc doit ÉCHOUER et le dire.
    if (!bouton) throw new Error("bouton « Ajouter un horaire » introuvable");
    await act(async () => { bouton.click(); });

    expect(axios.post).toHaveBeenCalled();
    const [url, corps] = axios.post.mock.calls[0];
    expect(String(url)).toContain('/courses');
    // LE POINT DU LOT : le nom commercial de l'offre ne part PAS.
    expect(corps.name).not.toBe("Cours à l'unité");
    expect(corps.name).toBe(NOM_PROVISOIRE);
    // Le LIEU, lui, est légitimement partagé : il continue d'être hérité.
    expect(corps.locationName).toBe(VAL);
    // Et la séance naît invisible : un horaire abandonné n'atteint pas la vitrine.
    expect(corps.visible).toBe(false);
  });

  test('deux fiches au même créneau et au même lieu sont SIGNALÉES', async () => {
    await monter([SILENT, DOUBLON], [DOUBLON.id]);
    const avert = conteneur.querySelector('[data-testid="v663-avertissement-doublon"]');
    expect(avert).toBeTruthy();
    expect(avert.textContent).toMatch(/existe déjà/i);
    // Il NOMME les deux fiches, pour que le coach sache laquelle garder.
    expect(avert.textContent).toMatch(/Session Cardio/);
    // Et il propose de rattacher, pas de fusionner.
    expect(avert.textContent).toMatch(/rattache/i);
  });

  test('deux cours RÉELLEMENT différents à la même heure ne sont pas signalés', async () => {
    // Même mercredi, même 18:45, mais un AUTRE lieu : deux créneaux légitimes.
    await monter([AILLEURS, SILENT], [SILENT.id]);
    expect(conteneur.querySelector('[data-testid="v663-avertissement-doublon"]')).toBeNull();
  });

  test('une offre reliée à PLUSIEURS cours n’en signale aucun', async () => {
    // Exemple 1 du cahier des charges, à l'envers : une offre peut viser
    // plusieurs cours autorisés — mercredi ici, et un dimanche ailleurs.
    const DIMANCHE = { ...SILENT, id: 'c-dim', name: 'Afroboost Silent – Sunday Vibes', weekday: 0, time: '18:30' };
    await monter([SILENT, DIMANCHE], [SILENT.id, DIMANCHE.id]);
    expect(conteneur.querySelector('[data-testid="v663-avertissement-doublon"]')).toBeNull();
  });

  test('aucune fusion, aucune suppression : le wizard n’écrit rien tout seul', async () => {
    await monter([SILENT, DOUBLON], [DOUBLON.id]);
    // L'avertissement s'affiche, mais AUCUNE requête n'est partie.
    expect(conteneur.querySelector('[data-testid="v663-avertissement-doublon"]')).toBeTruthy();
    expect(axios.post).not.toHaveBeenCalled();
    expect(axios.put).not.toHaveBeenCalled();
    expect(axios.delete).toBeUndefined();   // le mouchard n'expose même pas delete
  });
});

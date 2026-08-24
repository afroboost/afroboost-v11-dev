/**
 * LE VRAI WIZARD, LE VRAI GESTE DU COACH.
 *
 * Scenario tel qu'il est vecu sur « 🎁 Cours d'essai GRATUIT » : l'offre porte
 * DEJA deux horaires recurrents ; le coach en ajoute un troisieme et veut en
 * faire une DATE UNIQUE (samedi 29 aout 14:30). Avant ce lot, le bouton
 * « Date unique » ne repondait pas : il posait `date: ''`, or le champ date
 * n'est revele que si `date` est NON VIDE. Le bloc restait hebdomadaire.
 *
 * Ce banc pilote le composant REEL et lit ce qui part au serveur (`axios.put`).
 * Aucune requete ne sort : axios est un mouchard.
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

// L'etat REEL de production, lu en base : trois blocs, tous recurrents.
const LUNDI = { id: 'c-lundi', name: 'Silent lundi', weekday: 1, date: '', time: '18:30',
  locationName: 'Neuchatel', coach_id: COACH, visible: true };
const MERCREDI = { id: 'c-mercredi', name: 'Silent mercredi', weekday: 3, date: '', time: '18:30',
  locationName: 'Neuchatel', coach_id: COACH, visible: true };
const TROISIEME = { id: 'c-samedi', name: 'Silent samedi', weekday: 1, date: '', time: '14:25',
  locationName: 'Neuchatel', coach_id: COACH, visible: true };

const OFFRE = {
  id: 'offre-essai', name: "🎁 Cours d'essai GRATUIT", price: 0,
  linked_course_ids: [LUNDI.id, MERCREDI.id, TROISIEME.id],
};

let conteneur, racine, sauvegardee;

async function monter(courses = [LUNDI, MERCREDI, TROISIEME], offre = OFFRE) {
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
  // Etape 2 « Logistique » : c'est la que vivent les horaires.
  await cliquer('[data-testid="wizard-step-2"], [data-step="2"]', true);
}

async function cliquer(selecteur, tolerant = false) {
  const el = conteneur.querySelector(selecteur);
  if (!el) {
    if (tolerant) return false;
    throw new Error(`introuvable : ${selecteur}`);
  }
  await act(async () => { el.click(); });
  return true;
}

async function allerEtape2() {
  // Les onglets d'etapes portent leur numero en texte ; on prend le bouton
  // « Logistique » par son libelle, comme le coach.
  const btn = [...conteneur.querySelectorAll('button')]
    .find(b => (b.textContent || '').trim().includes('Logistique'));
  if (btn) await act(async () => { btn.click(); });
}

async function saisir(selecteur, valeur) {
  const el = conteneur.querySelector(selecteur);
  if (!el) throw new Error(`introuvable : ${selecteur}`);
  const setter = Object.getOwnPropertyDescriptor(
    el.constructor.prototype, 'value').set;
  await act(async () => {
    setter.call(el, valeur);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

async function enregistrer() {
  // Le bouton « Enregistrer » ne vit qu'a l'etape 3 : on traverse le wizard
  // comme le coach, par « Suivant » — ce qui eprouve aussi la traversee.
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

/** Les payloads d'horaires reellement envoyes, indexes par id de cours. */
function payloadsEnvoyes() {
  const out = {};
  for (const appel of axios.put.mock.calls) {
    const id = String(appel[0]).split('/').pop();
    out[id] = appel[1];
  }
  return out;
}

beforeEach(async () => {
  jest.clearAllMocks();
  axios.put.mockResolvedValue({ data: {} });
  axios.post.mockResolvedValue({ data: { id: 'c-neuf', name: 'Nouveau cours', weekday: 3, date: '', time: '18:30' } });
  await monter();
  await allerEtape2();
});

afterEach(async () => {
  await act(async () => { racine.unmount(); });
  conteneur.remove();
});

describe('le bouton « Date unique »', () => {
  test('LE BUG : sur un bloc recurrent, il doit reveler le champ DATE', async () => {
    expect(conteneur.querySelector(`[data-testid="weekday-${TROISIEME.id}"]`)).toBeTruthy();
    await cliquer(`[data-testid="recurrence-ponctuel-${TROISIEME.id}"]`);
    // Le selecteur de jour disparait, l'input date apparait : c'est TOUT ce que
    // le coach demandait, et c'est ce qui ne se produisait pas.
    expect(conteneur.querySelector(`[data-testid="weekday-${TROISIEME.id}"]`)).toBeNull();
    expect(conteneur.querySelector(`[data-testid="recurrence-${TROISIEME.id}"]`)).toBeTruthy();
    expect(conteneur.querySelector('input[type="date"]')).toBeTruthy();
  });

  test('il n\'affecte QUE son bloc — les deux autres restent hebdomadaires', async () => {
    await cliquer(`[data-testid="recurrence-ponctuel-${TROISIEME.id}"]`);
    expect(conteneur.querySelector(`[data-testid="weekday-${LUNDI.id}"]`)).toBeTruthy();
    expect(conteneur.querySelector(`[data-testid="weekday-${MERCREDI.id}"]`)).toBeTruthy();
  });

  test('« Chaque semaine » ramene le bloc en recurrent', async () => {
    await cliquer(`[data-testid="recurrence-ponctuel-${TROISIEME.id}"]`);
    await cliquer(`[data-testid="recurrence-hebdo-${TROISIEME.id}"]`);
    expect(conteneur.querySelector(`[data-testid="weekday-${TROISIEME.id}"]`)).toBeTruthy();
  });
});

describe('LE CAS DU PROPRIETAIRE : 2 recurrents + 1 date unique', () => {
  test('les trois blocs partent au serveur avec CHACUN son type', async () => {
    await cliquer(`[data-testid="recurrence-ponctuel-${TROISIEME.id}"]`);
    await saisir('input[type="date"]', '2026-08-29');
    await enregistrer();

    const envoyes = payloadsEnvoyes();
    expect(envoyes[TROISIEME.id]).toMatchObject({ date: '2026-08-29', weekday: 6 });
    // Les deux recurrents n'ont pas ete touches : ils ne sont donc PAS
    // reenvoyes. S'ils l'etaient, ils devraient l'etre a l'identique.
    for (const bloc of [LUNDI, MERCREDI]) {
      if (envoyes[bloc.id]) {
        expect(envoyes[bloc.id].date).toBe('');
        expect(envoyes[bloc.id].weekday).toBe(bloc.weekday);
      }
    }
    expect(sauvegardee).toBeTruthy();
    expect(sauvegardee.linked_course_ids).toEqual(
      [LUNDI.id, MERCREDI.id, TROISIEME.id]);
  });

  test('on ne devine pas la date : « Date unique » sans date BLOQUE, sans convertir', async () => {
    await cliquer(`[data-testid="recurrence-ponctuel-${TROISIEME.id}"]`);
    await enregistrer();
    expect(sauvegardee).toBeNull();
    expect(conteneur.textContent).toMatch(/Date unique/);
    expect(payloadsEnvoyes()[TROISIEME.id]).toBeUndefined();
  });
});

describe('PROTECTION DES HORAIRES EXISTANTS', () => {
  test('ouvrir puis enregistrer sans rien toucher n\'envoie AUCUN horaire', async () => {
    await enregistrer();
    expect(axios.put).not.toHaveBeenCalled();
    expect(sauvegardee.linked_course_ids).toEqual(
      [LUNDI.id, MERCREDI.id, TROISIEME.id]);
  });

  test('un bloc DEJA ponctuel reste ponctuel apres un aller-retour sans modification', async () => {
    await act(async () => { racine.unmount(); });
    conteneur.remove();
    const dejaUnique = { ...TROISIEME, date: '2026-08-29', weekday: 6 };
    await monter([LUNDI, MERCREDI, dejaUnique],
      { ...OFFRE, linked_course_ids: [LUNDI.id, MERCREDI.id, dejaUnique.id] });
    await allerEtape2();
    expect(conteneur.querySelector('input[type="date"]').value).toBe('2026-08-29');
    await enregistrer();
    expect(axios.put).not.toHaveBeenCalled();
  });

  test('retirer UN horaire laisse les deux autres intacts', async () => {
    const avant = (sauvegardee || {});
    const boutons = conteneur.querySelectorAll('[aria-label="Retirer cet horaire de l\'offre"]');
    expect(boutons.length).toBe(3);
    await act(async () => { boutons[1].click(); });
    await enregistrer();
    expect(sauvegardee.linked_course_ids).toEqual([LUNDI.id, TROISIEME.id]);
    expect(avant).toBeTruthy();
  });
});

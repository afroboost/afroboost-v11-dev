/**
 * V646 — l'écran montre les BROUILLONS avant tout envoi.
 * Données calquées sur « AFROBOOST CORPORATE — NEUCHÂTEL » (état `preparee`).
 * Aucune écriture : le composant reste en lecture seule.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import MessagesRelancesSection from '../MessagesRelancesSection';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), patch: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));

jest.mock('../../../hooks/useChargement', () => {
  const R = jest.requireActual('react');
  const SECTION = { ATTENTE: 'attente', CHARGEMENT: 'chargement', OK: 'ok', ERREUR: 'erreur', SESSION: 'session' };
  return {
    __esModule: true,
    SECTION,
    default: (sources) => {
      const cles = Object.keys(sources).join('|');
      const [sections, setSections] = R.useState(() => Object.fromEntries(
        Object.keys(sources).map((k) => [k, { etat: SECTION.CHARGEMENT, donnees: null }])));
      const ref = R.useRef(sources); ref.current = sources;
      R.useEffect(() => {
        Object.keys(ref.current).forEach((k) => {
          ref.current[k].appel().then(
            (d) => setSections((p) => ({ ...p, [k]: { etat: SECTION.OK, donnees: d } })),
            () => setSections((p) => ({ ...p, [k]: { etat: SECTION.ERREUR, donnees: null, motif: 'serveur' } })));
        });
      }, [cles]);
      return { sections, reessayer: jest.fn() };
    },
  };
});

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const EMAIL_OK = 'Objet : Une expérience originale pour vos équipes\n\nBonjour,\n\nJe suis Coach Bassi, d’Afroboost à Neuchâtel.';
const base = (id, org, sur) => Object.assign({
  id, recipient_key: id, organisations: [org], prospect_ids: [id],
  channel: 'email', execution_type: 'AUTO', statut: 'pret',
  message_j0: EMAIL_OK, message_j0_origine: 'edite', updated_at: '2026-11-10T03:00:00+00:00',
}, sur || {});

const ACTIONS = [
  base('CORP-NE-01', 'Costaud'),
  base('CORP-NE-02', 'KEZIA'),
  base('CORP-NE-03', 'Interoffice', { message_j0: 'Bonjour,\n\nSans objet.' }),          // brouillon
  base('CORP-NE-04', 'Vivatax', { channel: 'telephone', execution_type: 'MANUEL',
    message_j0: 'SCRIPT D’APPEL\n\nBonjour, je suis Coach Bassi.' }),
  base('CORP-NE-11', 'IPAS architectes', { channel: 'aucun', execution_type: 'BLOQUE', statut: 'bloque',
    message_j0: '', message_j0_origine: 'absent', execution_reason: 'aucune coordonnee numerique exploitable' }),
];

let ETAT_CAMPAGNE = 'preparee';
const campagne = () => ({ id: 'cne', nom: 'AFROBOOST CORPORATE — NEUCHÂTEL', etat: ETAT_CAMPAGNE });

function serveur(url) {
  if (url === '/api/prospect-campaigns') return { campaigns: [campagne()] };
  if (url === '/api/prospect-campaigns/cne') return { campaign: campagne(), actions: ACTIONS };
  if (url === '/api/prospect-inbound') return { conversations: [], messages: [] };
  if (url === '/api/partner-prospects') return { total: 0, prospects: [] };
  if (url === '/api/feature-flags') return { P3_RELANCE_ENABLED: false, P3_RELANCE_ENVOI_REEL: false };
  if (/\/(notes|brouillon)$/.test(url)) return { notes: [], brouillon: null };
  throw new Error(`URL inattendue ${url}`);
}

let conteneur; let racine;
const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const tous = (id) => Array.from(conteneur.querySelectorAll(`[data-testid="${id}"]`));
const attendre = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
async function cliquer(el) { await act(async () => { el.click(); }); await attendre(); await attendre(); }
const tuile = (id) => par(id).lastChild.textContent;

async function monter() {
  axios.get.mockImplementation((url) => Promise.resolve({ data: serveur(url) }));
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(<MessagesRelancesSection API="/api" actif />); });
  await attendre(); await attendre();
}

afterEach(async () => {
  if (racine) await act(async () => racine.unmount());
  if (conteneur) conteneur.remove();
  racine = null; conteneur = null;
  ETAT_CAMPAGNE = 'preparee';
  jest.clearAllMocks();
});

test('campagne « preparee » : la bande « Avant envoi » compte brouillons, à relire, prêts, bloqués', async () => {
  await monter();
  expect(par('mr-avant-envoi')).toBeTruthy();
  /* Un seul brouillon : Interoffice (objet manquant). La fiche SANS coordonnée
     compte comme « bloquée », pas comme brouillon — on ne demande pas au coach
     de compléter un texte qui n'a de toute façon aucun canal pour partir. */
  expect(tuile('mr-c-brouillons')).toBe('1');
  expect(tuile('mr-c-a_relire')).toBe('3');
  expect(tuile('mr-c-prets')).toBe('0');
  expect(tuile('mr-c-bloques')).toBe('1');
});

test('le badge « Brouillon » est posé sur la ligne concernée, et sur elle seule', async () => {
  await monter();
  const brouillons = tous('mr-preparation').filter((b) => b.getAttribute('data-preparation') === 'brouillon');
  expect(brouillons).toHaveLength(1);
  const ligne = brouillons[0].closest('[data-testid="mr-ligne"]');
  expect(ligne.textContent).toContain('Interoffice');
  expect(ligne.textContent).toContain('objet manquant');
});

test('le filtre « Brouillons » ne laisse que les brouillons', async () => {
  await monter();
  await cliquer(par('mr-filtre-brouillons'));
  expect(tous('mr-ligne')).toHaveLength(1);
  expect(par('mr-resultat').textContent).toContain('1 destinataire');
});

test('le dossier ouvert dit l’état, ce qui manque et ce qu’il faut faire', async () => {
  await monter();
  const brouillon = tous('mr-preparation').find((b) => b.getAttribute('data-preparation') === 'brouillon');
  await cliquer(brouillon.closest('[data-testid="mr-ligne"]').querySelector('[data-testid="mr-ligne-entete"]'));
  const bandeau = document.body.querySelector('[data-testid="mr-panneau-preparation"]');
  expect(bandeau).toBeTruthy();
  expect(bandeau.textContent).toContain('Brouillon');
  expect(bandeau.textContent).toContain('objet manquant');
  expect(bandeau.textContent).toContain('Compléter');
});

test('campagne APPROUVÉE : la bande disparaît et les messages complets passent « Prêt »', async () => {
  ETAT_CAMPAGNE = 'approuvee';
  await monter();
  expect(par('mr-avant-envoi')).toBeNull();
  const prets = tous('mr-preparation').filter((b) => b.getAttribute('data-preparation') === 'pret');
  expect(prets).toHaveLength(3);
});

test('aucune écriture : ni POST, ni PATCH, ni PUT, ni DELETE', async () => {
  await monter();
  await cliquer(par('mr-filtre-brouillons'));
  expect(axios.post).not.toHaveBeenCalled();
  expect(axios.patch).not.toHaveBeenCalled();
  expect(axios.put).not.toHaveBeenCalled();
  expect(axios.delete).not.toHaveBeenCalled();
});

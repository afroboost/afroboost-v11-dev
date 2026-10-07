// V588 — l'écran « Messages & relances » : lecture seule, textes APPROUVÉS, aucune écriture.
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import MessagesRelancesSection from '../MessagesRelancesSection';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), patch: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));

/* Chargeur minimal : exécute chaque `appel` une fois (le vrai portillon JWT n'a pas
   sa place dans ce test). Dépendances primitives, comme le vrai. */
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

const CAMPAGNE = { id: 'c1', name: 'P3-LAUNCH-137', etat: 'approuvee',
  subject_j0: 'Proposition de collaboration', subject_j3: 'Re: Proposition de collaboration', subject_j7: 'Re: Proposition de collaboration' };
const envoyee = (id, org, sur) => Object.assign({
  id, recipient_key: id.toUpperCase(), organisations: [org], prospect_ids: [id.toUpperCase()],
  channel: 'email', execution_type: 'AUTO', statut: 'envoye', message_j0: `J0 ${org}`,
  message_j3: `RELANCE J3 APPROUVÉE ${org}`, message_j7: `RELANCE J7 APPROUVÉE ${org}`,
  sent_at: '2026-09-03T10:57:00+00:00', provider_message_id: 'r', provider_status: 'accepted',
  j3_due_at: '2026-09-06T10:57:00+00:00', j7_due_at: '2026-09-10T10:57:00+00:00',
}, sur || {});
const ACTIONS = [
  envoyee('a-fen', 'FEN'),
  envoyee('a-bde', 'BDE HE-Arc', { replied_at: '2026-09-04T05:25:19Z', j3_annule_le: '2026-09-04T05:25:20Z',
    j3_annule_motif: 'reponse recue', j7_annule_le: '2026-09-04T05:25:20Z', j7_annule_motif: 'reponse recue' }),
  envoyee('a-dead', 'Case à Chocs', { bounce_type: 'Permanent', j3_annule_le: '2026-09-03T11:00:00Z', j3_annule_motif: 'rebond permanent' }),
  { id: 'a-akoko', recipient_key: 'COM-01', organisations: ['Akoko Tresses'], prospect_ids: ['COM-01'],
    channel: 'instagram', execution_type: 'MANUEL', statut: 'pret', message_j0: 'Salut Akoko' },
];
const CONVERSATIONS = [{ action_id: 'a-bde', organisation: 'BDE HE-Arc', nb_messages: 1, message_ids: ['m-bde'],
  statut_commercial: 'en_attente', messages_recus: [{ id: 'm-bde', received_at: '2026-09-04T05:25:19Z', subject: 'Re: Proposition' }],
  derniere_reponse_afroboost: { sent_at: '2026-09-08T09:48:24Z', objet: 'Re: Proposition' } }];
/* La FICHE porte un brouillon NON approuvé : il ne doit jamais apparaître. */
const PROSPECTS = [{ ref: 'A-FEN', status: 'contacte', j3_message: 'BROUILLON FICHE NON APPROUVÉ' },
  { ref: 'A-BDE', status: 'repondu' }];

function serveur(url) {
  if (url === '/api/prospect-campaigns') return { campaigns: [CAMPAGNE] };
  if (url === '/api/prospect-campaigns/c1') return { campaign: CAMPAGNE, actions: ACTIONS };
  if (url === '/api/prospect-inbound') return { conversations: CONVERSATIONS, messages: [] };
  if (url === '/api/partner-prospects') return { total: 2, prospects: PROSPECTS };
  if (url === '/api/feature-flags') return { P3_RELANCE_ENABLED: false, P3_RELANCE_ENVOI_REEL: false };
  if (url === '/api/prospect-inbound/m-bde/notes') {
    return { notes: [{ id: 'n1', type: 'appel', texte: 'Comité contacté', occurred_at: '2026-09-09T09:00:00Z' }] };
  }
  throw new Error(`URL inattendue ${url}`);
}

let conteneur; let racine;
const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const tous = (id) => Array.from(conteneur.querySelectorAll(`[data-testid="${id}"]`));
const attendre = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
async function cliquer(el) { await act(async () => { el.click(); }); await attendre(); }
const tuile = (id) => par(id).lastChild.textContent;

beforeEach(async () => {
  axios.get.mockImplementation((url) => Promise.resolve({ data: serveur(url) }));
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(<MessagesRelancesSection API="/api" />); });
  await attendre(); await attendre();
});
afterEach(async () => {
  await act(async () => { racine.unmount(); });
  document.body.removeChild(conteneur);
  jest.clearAllMocks();
});

test('compteurs calculés sur les vraies données', () => {
  expect(tuile('mr-c-total')).toBe('4');
  expect(tuile('mr-c-j0')).toBe('3');
  expect(tuile('mr-c-j3-retard')).toBe('1');
  expect(tuile('mr-c-j3-avenir')).toBe('0');
  expect(tuile('mr-c-j7-avenir')).toBe('1');
  expect(tuile('mr-c-reponses')).toBe('1');
  expect(tuile('mr-c-stoppes')).toBe('1');
  expect(tuile('mr-c-manuel')).toBe('1');
  expect(par('mr-interrupteurs').textContent).toContain('fermées');
});

test('filtre « J+3 en retard » puis détail : message APPROUVÉ, jamais le brouillon de la fiche', async () => {
  await cliquer(par('mr-filtre-en_retard'));
  const lignes = tous('mr-ligne');
  expect(lignes).toHaveLength(1);
  expect(lignes[0].textContent).toContain('FEN');
  expect(lignes[0].textContent).toMatch(/J\+3 · en retard \d+ j/);
  await cliquer(par('mr-ligne-entete'));
  expect(par('mr-message-j3').textContent).toBe('RELANCE J3 APPROUVÉE FEN');
  expect(conteneur.textContent).not.toContain('BROUILLON FICHE');
  expect(par('mr-chronologie').textContent).toContain('J+3 en retard');
});

test('réponse : J+3/J+7 annulés, réponse Afroboost et notes dans l\'historique', async () => {
  await cliquer(par('mr-filtre-repondus'));
  expect(tous('mr-ligne')).toHaveLength(1);
  await cliquer(par('mr-ligne-entete'));
  await attendre();
  const h = par('mr-chronologie').textContent;
  expect(h).toContain('Réponse reçue');
  expect(h).toContain('J+3 annulé');
  expect(h).toContain('J+7 annulé');
  expect(h).toContain('Réponse envoyée par Afroboost');
  expect(h).toContain('Comité contacté');
});

test('DM Instagram : « Suivi manuel non encore disponible », filtres Manuel et canal DM', async () => {
  await cliquer(par('mr-canal-dm'));
  expect(tous('mr-ligne')).toHaveLength(1);
  await cliquer(par('mr-ligne-entete'));
  expect(par('mr-suivi-manuel').textContent).toContain('Suivi manuel non encore disponible');
  await cliquer(par('mr-canal-tous'));
  await cliquer(par('mr-filtre-manuel'));
  expect(tous('mr-ligne').map((l) => l.dataset.etat)).toEqual(['manuel']);
});

test('aucune écriture : seuls des GET partent, et aucun bouton d\'envoi', async () => {
  for (const l of tous('mr-ligne-entete')) await cliquer(l);
  for (const f of ['tous', 'a_envoyer', 'en_retard', 'envoyes', 'repondus', 'stoppes', 'manuel']) await cliquer(par(`mr-filtre-${f}`));
  expect(axios.post).not.toHaveBeenCalled();
  expect(axios.patch).not.toHaveBeenCalled();
  expect(axios.put).not.toHaveBeenCalled();
  expect(axios.delete).not.toHaveBeenCalled();
  expect(Array.from(conteneur.querySelectorAll('button')).some((b) => /^\s*(envoyer|activer|relancer|lancer)/i.test(b.textContent))).toBe(false);
  /* Les notes ne sont lues qu'une fois par dossier. */
  expect(axios.get.mock.calls.filter(([u]) => /notes$/.test(u))).toHaveLength(1);
});

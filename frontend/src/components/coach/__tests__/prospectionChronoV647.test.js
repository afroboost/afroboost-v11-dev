/**
 * V647 — l'écran : filtres rapides, « Derniers envois », dates véridiques,
 * aperçu de l'e-mail. LECTURE SEULE : aucune écriture, jamais.
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

const J = 86400000;
const MAINTENANT = Date.now();
const iso = (ms) => new Date(ms).toISOString();

const base = (id, org, sur) => Object.assign({
  id, recipient_key: id, organisations: [org], prospect_ids: [id],
  channel: 'email', execution_type: 'AUTO', statut: 'pret',
  message_j0: `Objet : Proposition ${org}\n\nBonjour,\n\nJe suis Coach Bassi, d’Afroboost à Neuchâtel.`,
  message_j0_origine: 'edite', target: `${id}@exemple.ch`,
  created_at: iso(MAINTENANT - 20 * J), updated_at: iso(MAINTENANT - 20 * J),
}, sur || {});

const ACTIONS = [
  base('A-FRAIS', 'Fraîchement envoyée', { sent_at: iso(MAINTENANT - 3 * 3600000) }),   // < 24 h
  base('A-VIEUX', 'Envoyée il y a longtemps', { sent_at: iso(MAINTENANT - 40 * J) }),
  base('A-PRET', 'Jamais envoyée'),
  base('A-BROUILLON', 'Sans objet', { message_j0: 'Bonjour, pas d’objet ici.' }),
  base('A-BLOQUE', 'Sans coordonnée', { channel: 'aucun', execution_type: 'BLOQUE', statut: 'bloque',
    message_j0: '', message_j0_origine: 'absent' }),
];

const CAMPAGNE = { id: 'cne', nom: 'AFROBOOST CORPORATE — NEUCHÂTEL', etat: 'preparee' };

function serveur(url) {
  if (url === '/api/prospect-campaigns') return { campaigns: [CAMPAGNE] };
  if (url === '/api/prospect-campaigns/cne') return { campaign: CAMPAGNE, actions: ACTIONS };
  if (url === '/api/prospect-inbound') return { conversations: [], messages: [] };
  if (url === '/api/partner-prospects') return { total: 0, prospects: [] };
  if (url === '/api/feature-flags') return { P3_RELANCE_ENABLED: false, P3_RELANCE_ENVOI_REEL: false };
  if (/\/apercu$/.test(url)) {
    return { objet: 'Proposition Fraîchement envoyée', destinataire: 'a-frais@exemple.ch',
      canal: 'email', texte: 'Bonjour,', media: { titre: 'AFROBOOST CORPORATE 16x9' },
      html_email: '<p>Aperçu</p>', envoye_le: iso(MAINTENANT - 3 * 3600000), statut: 'envoye' };
  }
  if (/\/(notes|brouillon)$/.test(url)) return { notes: [], brouillon: null };
  throw new Error(`URL inattendue ${url}`);
}

let conteneur; let racine;
const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const tous = (id) => Array.from(conteneur.querySelectorAll(`[data-testid="${id}"]`));
const attendre = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
async function cliquer(el) { await act(async () => { el.click(); }); await attendre(); await attendre(); }
const orgs = () => tous('mr-ligne').map((l) => l.querySelector('span').textContent);

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
  jest.clearAllMocks();
});

test('les huit filtres rapides sont affichés, avec leurs compteurs réels', async () => {
  await monter();
  expect(par('mr-rapides')).toBeTruthy();
  ['tous', 'brouillons', 'a_relire', 'prets', 'derniers_envois', 'en_attente_reponse', 'a_relancer', 'bloques']
    .forEach((id) => expect(par(`mr-rapide-${id}`)).toBeTruthy());
  expect(par('mr-rapide-derniers_envois').textContent).toContain('2');   // 2 envois réels
  expect(par('mr-rapide-brouillons').textContent).toContain('1');
});

test('« Derniers envois » ne montre que les envois RÉELS, le plus récent d’abord', async () => {
  await monter();
  await cliquer(par('mr-rapide-derniers_envois'));
  expect(orgs()).toEqual(['Fraîchement envoyée', 'Envoyée il y a longtemps']);
  expect(orgs()).not.toContain('Jamais envoyée');
});

test('une action préparée n’affiche AUCUNE date d’envoi', async () => {
  await monter();
  const ligne = tous('mr-ligne').find((l) => l.textContent.includes('Jamais envoyée'));
  expect(ligne.textContent).toContain('jamais envoyé');
  expect(ligne.querySelector('[data-testid="mr-carte-envoi"]')).toBeNull();
});

test('un envoi de moins de 24 h porte le repère discret', async () => {
  await monter();
  const frais = tous('mr-ligne').find((l) => l.textContent.includes('Fraîchement envoyée'));
  const vieux = tous('mr-ligne').find((l) => l.textContent.includes('Envoyée il y a longtemps'));
  expect(frais.querySelector('[data-testid="mr-recent"]')).toBeTruthy();
  expect(vieux.querySelector('[data-testid="mr-recent"]')).toBeNull();
  expect(vieux.querySelector('[data-testid="mr-carte-envoi"]')).toBeTruthy();
});

test('la campagne est nommée sur chaque ligne', async () => {
  await monter();
  expect(tous('mr-carte-campagne')[0].textContent).toBe('AFROBOOST CORPORATE — NEUCHÂTEL');
});

test('le tri chronologique est disponible et agit vraiment', async () => {
  await monter();
  const select = par('mr-tri');
  expect(Array.from(select.options).map((o) => o.value)).toEqual(
    ['priorite', 'activite', 'envoi_desc', 'envoi_asc', 'creation_desc', 'creation_asc', 'modif_desc']);
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, 'envoi_asc');
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await attendre();
  // Du plus ancien envoi au plus récent, puis ceux qui n'ont jamais été envoyés.
  expect(orgs().slice(0, 2)).toEqual(['Envoyée il y a longtemps', 'Fraîchement envoyée']);
});

test('le filtre de période écarte ce qui est hors fenêtre', async () => {
  await monter();
  const select = par('mr-periode');
  expect(Array.from(select.options).map((o) => o.value)).toEqual(['tout', 'aujourdhui', '7j', '30j', 'perso']);
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, 'aujourdhui');
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await attendre();
  expect(orgs()).toEqual(['Fraîchement envoyée']);
});

test('période et filtre rapide se combinent ; l’état vide est honnête', async () => {
  await monter();
  await cliquer(par('mr-rapide-brouillons'));
  const select = par('mr-periode');
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, 'aujourdhui');
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await attendre();
  expect(tous('mr-ligne')).toHaveLength(0);
  expect(par('mr-vide').textContent).toContain('Aucun destinataire ne correspond');
  // Sur « Derniers envois », le message dit la bonne chose.
  await cliquer(par('mr-rapide-derniers_envois'));
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(select, 'perso');
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await attendre();
  expect(par('mr-vide').textContent).toBe('Aucun message envoyé pour cette sélection.');
});

test('le dossier ouvert montre l’e-mail tel qu’il partira, vidéo comprise', async () => {
  await monter();
  const ligne = tous('mr-ligne').find((l) => l.textContent.includes('Fraîchement envoyée'));
  await cliquer(ligne.querySelector('[data-testid="mr-ligne-entete"]'));
  const panneau = document.body.querySelector('[data-testid="mr-panneau"]');
  const apercu = panneau.querySelector('[data-testid="mr-apercu"]');
  expect(apercu).toBeTruthy();
  expect(apercu.querySelector('[data-testid="mr-apercu-objet"]').textContent).toBe('Proposition Fraîchement envoyée');
  expect(apercu.querySelector('[data-testid="mr-apercu-video"]').textContent).toContain('AFROBOOST CORPORATE 16x9');
  const cadre = apercu.querySelector('[data-testid="mr-apercu-cadre"]');
  expect(cadre.getAttribute('sandbox')).toBe('');        // aucun script, aucune origine
  expect(cadre.getAttribute('srcdoc')).toContain('Aperçu');
});

test('les brouillons restent repérables et « preparee » est écrit en français', async () => {
  await monter();
  expect(par('mr-avant-envoi')).toBeTruthy();
  expect(par('mr-avant-envoi').textContent).toContain('à compléter avant d’approuver');
  // §6 : le code technique ne doit pas être montré tel quel au coach.
  const etat = par('mr-etat-campagne');
  expect(etat.textContent).toContain('Campagne préparée');
  expect(etat.textContent).toContain('non approuvée, non démarrée');
  expect(etat.textContent).toContain('aucun message ne peut partir');
  expect(etat.textContent).not.toMatch(/\bpreparee\b/);
});

test('AUCUNE écriture : consulter, trier, filtrer et ouvrir ne change rien', async () => {
  await monter();
  await cliquer(par('mr-rapide-derniers_envois'));
  const ligne = tous('mr-ligne')[0];
  await cliquer(ligne.querySelector('[data-testid="mr-ligne-entete"]'));
  expect(axios.post).not.toHaveBeenCalled();
  expect(axios.patch).not.toHaveBeenCalled();
  expect(axios.put).not.toHaveBeenCalled();
  expect(axios.delete).not.toHaveBeenCalled();
});

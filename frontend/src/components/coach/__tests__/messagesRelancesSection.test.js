// V588 / V588b — l'écran « Messages & relances » : lecture seule, textes APPROUVÉS,
// Nouveau / Appel à faire / Réponse attendue, partenaire à GAUCHE / Afroboost à DROITE, aucune écriture.
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

const CAMPAGNE = { id: 'c1', nom: 'P3-LAUNCH-137', etat: 'approuvee',
  subject_j0: 'Proposition de collaboration', subject_j3: 'Re: Proposition de collaboration', subject_j7: 'Re: Proposition de collaboration' };
const envoyee = (id, org, sur) => Object.assign({
  id, recipient_key: id.toUpperCase(), organisations: [org], prospect_ids: [id.toUpperCase()],
  channel: 'email', execution_type: 'AUTO', statut: 'envoye', target: `${id}@exemple.ch`, message_j0: `J0 APPROUVÉ ${org}`,
  message_j3: `RELANCE J3 APPROUVÉE ${org}`, message_j7: `RELANCE J7 APPROUVÉE ${org}`,
  sent_at: '2026-09-03T10:57:00+00:00', provider_message_id: 'r', provider_status: 'accepted',
  j3_due_at: '2026-09-06T10:57:00+00:00', j7_due_at: '2026-09-10T10:57:00+00:00',
}, sur || {});
const annuleReponse = { j3_annule_le: '2026-09-04T05:25:20Z', j3_annule_motif: 'reponse recue',
  j7_annule_le: '2026-09-04T05:25:20Z', j7_annule_motif: 'reponse recue' };
const ACTIONS = [
  envoyee('a-fen', 'FEN'),
  envoyee('a-bde', 'BDE HE-Arc', { replied_at: '2026-09-04T05:25:19Z', ...annuleReponse }),
  envoyee('a-new', 'Festival Nouveau', { replied_at: '2026-10-07T10:00:00Z', ...annuleReponse }),
  envoyee('a-urg', 'Entreprise Appel', { replied_at: '2026-10-06T10:00:00Z', ...annuleReponse }),
  envoyee('a-dyn', 'Dynam', { replied_at: '2026-09-10T10:00:00Z', ...annuleReponse }),
  envoyee('a-salsa', 'SalsaRica', { replied_at: '2026-09-05T10:00:00Z', ...annuleReponse }),
  envoyee('a-dead', 'Case à Chocs', { bounce_type: 'Permanent', j3_annule_le: '2026-09-03T11:00:00Z', j3_annule_motif: 'rebond permanent' }),
  { id: 'a-akoko', recipient_key: 'COM-01', organisations: ['Akoko Tresses'], prospect_ids: ['COM-01'],
    channel: 'instagram', execution_type: 'MANUEL', statut: 'pret', message_j0: 'Salut Akoko' },
];
const msg = (id, quand, texte, lu) => ({ id, received_at: quand, subject: 'Re: Proposition', from_email: 'contact@ex.ch',
  body_text: `${texte}\n\nLe 3 sept. 2026, Afroboost a écrit :\n> J0 cité`, read_at: lu ? '2026-09-05T10:00:00Z' : undefined });
const conv = (action_id, organisation, messages, sur) => Object.assign({
  action_id, organisation, nb_messages: messages.length, message_ids: messages.map((m) => m.id),
  messages_recus: messages, dernier_message: messages[messages.length - 1],
  non_lues: messages.filter((m) => !m.read_at).length, statut_commercial: 'en_attente',
  derniere_reponse_afroboost: null, reponse_apres_dernier_message: false,
}, sur || {});
const CONVERSATIONS = [
  conv('a-bde', 'BDE HE-Arc', [msg('m-bde1', '2026-09-04T05:25:19Z', 'Bonjour, ça consiste en quoi ?', true),
    msg('m-bde2', '2026-09-05T14:45:26Z', 'Nous en parlerons au comité.', true)],
  { derniere_reponse_afroboost: { sent_at: '2026-09-08T09:48:24Z', objet: 'Re: Proposition' }, reponse_apres_dernier_message: true }),
  conv('a-new', 'Festival Nouveau', [msg('m-new', '2026-10-07T13:48:00Z', 'Nous devons confirmer le programme avant vendredi.', false)],
    { statut_commercial: 'a_repondre' }),
  conv('a-urg', 'Entreprise Appel', [msg('m-urg', '2026-10-06T10:00:00Z', 'Pouvez-vous nous rappeler aujourd’hui ?', true)],
    { statut_commercial: 'appel_a_faire' }),
  conv('a-dyn', 'Dynam', [msg('m-dyn', '2026-09-10T10:00:00Z', 'Intéressés, quels tarifs ?', true)], { statut_commercial: 'a_repondre' }),
  conv('a-salsa', 'SalsaRica', [msg('m-salsa', '2026-09-05T10:00:00Z', 'Non merci.', true)], { statut_commercial: 'refus' }),
];
/* La FICHE porte un brouillon NON approuvé : il ne doit jamais apparaître. */
const PROSPECTS = [{ ref: 'A-FEN', status: 'contacte', city: 'Neuchâtel', category: 'festival', j3_message: 'BROUILLON FICHE NON APPROUVÉ' },
  { ref: 'A-BDE', status: 'repondu', city: 'Neuchâtel', category: 'etudiants' },
  { ref: 'COM-01', status: 'a_contacter', city: 'Genève', category: 'commerce', contact_name: 'Awa' }];

function serveur(url) {
  if (url === '/api/prospect-campaigns') return { campaigns: [CAMPAGNE] };
  if (url === '/api/prospect-campaigns/c1') return { campaign: CAMPAGNE, actions: ACTIONS };
  if (url === '/api/prospect-inbound') return { conversations: CONVERSATIONS, messages: [] };
  if (url === '/api/partner-prospects') return { total: PROSPECTS.length, prospects: PROSPECTS };
  if (url === '/api/feature-flags') return { P3_RELANCE_ENABLED: false, P3_RELANCE_ENVOI_REEL: false };
  if (url === '/api/prospect-inbound/m-bde1/notes') {
    return { notes: [{ id: 'n1', type: 'appel', texte: 'Comité contacté', occurred_at: '2026-09-09T09:00:00Z' }] };
  }
  if (/\/notes$/.test(url)) return { notes: [] };
  if (url === '/api/prospect-inbound/m-bde2/brouillon') {
    return { brouillon: { resume: 'Le BDE en parle au comité.', prochaine_action: 'Attendre la réponse du comité.',
      reponse_proposee: 'Merci pour votre retour, au plaisir !', updated_at: '2026-09-08T09:00:00Z' } };
  }
  if (/\/brouillon$/.test(url)) return { brouillon: null };
  throw new Error(`URL inattendue ${url}`);
}

let conteneur; let racine;
const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const tous = (id) => Array.from(conteneur.querySelectorAll(`[data-testid="${id}"]`));
const panneau = () => document.body.querySelector('[data-testid="mr-panneau"]');
const dansPanneau = (id) => Array.from((panneau() || document.createElement('div')).querySelectorAll(`[data-testid="${id}"]`));
const attendre = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
async function cliquer(el) { await act(async () => { el.click(); }); await attendre(); await attendre(); }
const tuile = (id) => par(id).lastChild.textContent;
const ligne = (org) => tous('mr-ligne').find((l) => l.textContent.startsWith(org) || l.textContent.includes(org));
async function ouvrir(org) { await cliquer(ligne(org).querySelector('[data-testid="mr-ligne-entete"]')); }
async function rechercher(q) {
  const champ = par('mr-recherche');
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(champ, q);
    champ.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

beforeEach(async () => {
  /* L'écran ne lit l'heure que par Date.now() : on fige SEULEMENT celle-ci. */
  jest.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-10-07T14:00:00Z'));
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
  jest.restoreAllMocks();
  jest.clearAllMocks();
});

test('compteurs principaux : à traiter, nouveaux, appels à faire, retards, réponses, stoppés', () => {
  expect(tuile('mr-c-a-traiter')).toBe('3');     // nouveau + appel à faire + Dynam (réponse attendue)
  expect(tuile('mr-c-nouveaux')).toBe('1');
  expect(tuile('mr-c-appels')).toBe('1');
  expect(par('mr-c-urgents')).toBeNull();                    // V588c : plus de compteur « Urgents »
  expect(tuile('mr-c-j3-retard')).toBe('1');     // FEN
  expect(tuile('mr-c-reponses')).toBe('5');
  expect(tuile('mr-c-stoppes')).toBe('2');       // SalsaRica (refus) + Case à Chocs (rebond)
  expect(par('mr-interrupteurs').textContent).toContain('fermées');
  expect(par('mr-stats').textContent).toContain('3 réponses attendues');   // nouveau + appel + Dynam
});

test('ordre de priorité : non lu → appel à faire → réponse attendue → J+3 en retard → manuel → reste', () => {
  const ordre = tous('mr-ligne').map((l) => l.querySelector('span').textContent);
  expect(ordre.slice(0, 5)).toEqual(['Festival Nouveau', 'Entreprise Appel', 'Dynam', 'FEN', 'Akoko Tresses']);
});

test('carte compacte : NOUVEAU (non lu), APPEL À FAIRE indépendant, réponse attendue, extrait sans citation', () => {
  const nouveau = ligne('Festival Nouveau');
  expect(nouveau.dataset.nouveau).toBe('oui');
  expect(nouveau.dataset.appel).toBe('non');
  expect(nouveau.querySelector('[data-testid="mr-badge-nouveau"]')).toBeTruthy();
  expect(nouveau.querySelector('[data-testid="mr-extrait"]').textContent).toContain('Nous devons confirmer le programme avant vendredi.');
  expect(nouveau.textContent).not.toContain('J0 cité');
  expect(nouveau.textContent).toContain('Réponse reçue il y a 12 min');

  const appel = ligne('Entreprise Appel');
  expect(appel.dataset.appel).toBe('oui');
  expect(appel.dataset.nouveau).toBe('non');                  // déjà lu, mais toujours un appel à faire
  expect(appel.querySelector('[data-testid="mr-badge-appel"]').textContent).toContain('Appel à faire');
  expect(appel.querySelector('[data-testid="mr-badge-nouveau"]')).toBeNull();
  /* V588c : aucune urgence n'est affichée — même pour « confirmer avant vendredi ». */
  expect(document.body.textContent).not.toMatch(/urgent/i);

  const dynam = ligne('Dynam');
  expect(dynam.dataset.attendue).toBe('oui');
  expect(dynam.textContent).toContain('Prochaine action : Répondre au partenaire');

  const bde = ligne('BDE HE-Arc');                              // lu, Afroboost a répondu
  expect(bde.dataset.nouveau).toBe('non');
  expect(bde.dataset.attendue).toBe('non');
});

test('filtre « À traiter » : nouveaux + appels à faire + réponses attendues, pas les 45 relances', async () => {
  await cliquer(par('mr-filtre-a_traiter'));
  expect(tous('mr-ligne').map((l) => l.querySelector('span').textContent)).toEqual(['Festival Nouveau', 'Entreprise Appel', 'Dynam']);
});

test('recherche instantanée : organisation, ville, catégorie, nom', async () => {
  await rechercher('bde');
  expect(tous('mr-ligne')).toHaveLength(1);
  await rechercher('Akoko');
  expect(tous('mr-ligne')[0].textContent).toContain('Akoko');
  await rechercher('neuchatel');
  expect(tous('mr-ligne')).toHaveLength(2);
  await rechercher('festival');                                   // nom ET catégorie
  expect(tous('mr-ligne').map((l) => l.querySelector('span').textContent)).toEqual(['Festival Nouveau', 'FEN']);
  await rechercher('awa');
  expect(tous('mr-ligne')).toHaveLength(1);
  await rechercher('');
  expect(tous('mr-ligne')).toHaveLength(ACTIONS.length);
});

test('panneau BDE : partenaire à GAUCHE, Afroboost à DROITE, réponse Afroboost, analyse IA, notes', async () => {
  await ouvrir('BDE HE-Arc');
  expect(panneau()).toBeTruthy();
  expect(conteneur.contains(panneau())).toBe(false);            // portail : rendu dans <body>
  const partenaires = dansPanneau('mr-bulle-partenaire');
  const afroboost = dansPanneau('mr-bulle-afroboost');
  expect(partenaires).toHaveLength(2);
  expect(partenaires.every((b) => b.dataset.cote === 'partenaire' && b.style.justifyContent === 'flex-start')).toBe(true);
  expect(afroboost.every((b) => b.dataset.cote === 'afroboost' && b.style.justifyContent === 'flex-end')).toBe(true);
  expect(partenaires[0].textContent).toContain('Partenaire');
  expect(afroboost[0].textContent).toContain('Afroboost');
  const texte = panneau().textContent;
  expect(texte).toContain('Merci pour votre retour, au plaisir !');   // brouillon validé AVANT l'envoi
  expect(texte).toContain('Texte du brouillon validé');
  expect(texte).toContain('Le BDE en parle au comité.');
  expect(texte).toContain('Comité contacté');
  expect(texte).toContain('J+3 annulé');
  expect(dansPanneau('mr-derniere-afroboost')[0].textContent).toBe('08/09/2026');
  /* Ordre du fil : J0 (Afroboost) → réponse 04/09 → … → réponse Afroboost 08/09. */
  const cotes = dansPanneau('mr-fil')[0].querySelectorAll('[data-cote]');
  expect(Array.from(cotes).map((b) => b.dataset.cote)).toEqual(['afroboost', 'partenaire', 'partenaire', 'afroboost']);
  await cliquer(dansPanneau('mr-retour')[0]);
  expect(panneau()).toBeNull();
});

test('panneau Dynam : « Réponse attendue » et aucune réponse Afroboost', async () => {
  await ouvrir('Dynam');
  expect(dansPanneau('mr-derniere-afroboost')[0].textContent).toBe('Aucune · Réponse attendue');
  expect(dansPanneau('mr-panneau-action')[0].textContent).toBe('Répondre au partenaire');
});

test('J+3 en retard : message APPROUVÉ, jamais le brouillon de la fiche', async () => {
  await cliquer(par('mr-filtre-en_retard'));
  expect(tous('mr-ligne')).toHaveLength(1);
  expect(tous('mr-ligne')[0].textContent).toMatch(/en retard de \d+ j/);
  await ouvrir('FEN');
  expect(dansPanneau('mr-message-j3')[0].textContent).toBe('RELANCE J3 APPROUVÉE FEN');
  expect(document.body.textContent).not.toContain('BROUILLON FICHE');
});

test('refus et rebond : visibles dans Stoppés', async () => {
  await cliquer(par('mr-filtre-stoppes'));
  expect(tous('mr-ligne').map((l) => l.dataset.etat).sort()).toEqual(['rebond', 'refus']);
});

test('DM Instagram : « Suivi manuel », rien supposé envoyé', async () => {
  await cliquer(par('mr-canal-dm'));
  expect(tous('mr-ligne')).toHaveLength(1);
  expect(tous('mr-ligne')[0].textContent).toContain('Suivi manuel');
  await ouvrir('Akoko');
  expect(dansPanneau('mr-suivi-manuel')[0].textContent).toContain('suivi manuel non encore disponible');
  expect(dansPanneau('mr-bulle-afroboost')).toHaveLength(0);
});

test('AUCUNE écriture : ni à l\'affichage, ni à l\'ouverture des dossiers, ni aux filtres', async () => {
  for (const org of ['Festival Nouveau', 'BDE HE-Arc', 'Dynam', 'Akoko Tresses']) {
    await ouvrir(org);
    await cliquer(dansPanneau('mr-fermer')[0]);
  }
  for (const f of ['tous', 'a_traiter', 'nouveaux', 'appels', 'en_retard', 'repondus', 'envoyes', 'stoppes', 'manuel']) await cliquer(par(`mr-filtre-${f}`));
  expect(axios.post).not.toHaveBeenCalled();
  expect(axios.patch).not.toHaveBeenCalled();
  expect(axios.put).not.toHaveBeenCalled();
  expect(axios.delete).not.toHaveBeenCalled();
  /* Le nouveau message reste NOUVEAU : ouvrir le dossier ici ne le marque pas lu. */
  await cliquer(par('mr-filtre-tous'));
  expect(ligne('Festival Nouveau').dataset.nouveau).toBe('oui');
  expect(Array.from(document.body.querySelectorAll('button')).some((b) => /^\s*(envoyer|activer|relancer|lancer)/i.test(b.textContent))).toBe(false);
});

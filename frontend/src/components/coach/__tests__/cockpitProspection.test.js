// V587c — COCKPIT CAMPAGNES → PROSPECTION : une seule source de vérité, aucune boucle.
//
// Monte le VRAI hook `useCockpitProspection` et le VRAI `ProspectsSection`, dans un
// cockpit miniature qui reproduit le câblage de CoachDashboard (mode Clients |
// Prospection, barre de sections Prospects / Conversations partenaires).
// V587b bouclait au remontage (deux sources de vérité synchronisées dans les deux sens).
// `axios` et `useChargement` sont mockés : aucun appel réseau.
import React, { useState, Profiler } from 'react';
import { createRoot } from 'react-dom/client';
import ProspectsSection from '../ProspectsSection';
import MessagesRelancesSection from '../MessagesRelancesSection';
import useCockpitProspection from '../../../hooks/useCockpitProspection';

jest.mock('axios', () => ({
  __esModule: true,
  default: { get: jest.fn(() => Promise.resolve({ data: {} })), patch: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));

let mockEtatParSection = null;
jest.mock('../../../hooks/useChargement', () => ({
  __esModule: true,
  SECTION: { ATTENTE: 'attente', CHARGEMENT: 'chargement', OK: 'ok', ERREUR: 'erreur', SESSION: 'session' },
  default: (sources) => {
    const sections = {};
    Object.keys(sources).forEach((cle) => {
      const e = (mockEtatParSection && mockEtatParSection[cle]) || { etat: 'ok', donnees: null };
      sections[cle] = { etat: e.etat, donnees: e.donnees, motif: 'serveur' };
    });
    return { sections, reessayer: jest.fn(), global: 'ok', donnees: {}, cles: Object.keys(sources),
             chargement: false, sessionExpiree: false };
  },
}));

global.IS_REACT_ACT_ENVIRONMENT = true;
const act = React.act;

const prospect = (sur) => Object.assign({
  id: 'p-1', ref: 'FES-01', organisation_name: "Festi'neuch", category: 'festival', city: 'Neuchâtel',
  status: 'a_contacter', priority: 'B', score: 6.5, preferred_channel: 'DM',
}, sur || {});

const message = (id, action, org) => ({
  id, action_id: action, recipient_key: action, from_email: `${action}@ex.test`,
  subject: 'Re: Proposition', body_text: 'Bonjour', received_at: '2026-09-04T05:25:19+00:00',
  statut: 'rattache', statut_commercial: 'en_attente', _organisation: org,
});

function donneesTest() {
  const msgs = [message('m-bde', 'a-bde', 'BDE HE-Arc'), message('m-dyn', 'a-dyn', 'Dynam')];
  const conversations = msgs.map((m) => ({
    cle: m.action_id, action_id: m.action_id, organisation: m._organisation, recipient_key: m.recipient_key,
    from_email: m.from_email, nb_messages: 1, message_ids: [m.id], non_lues: 0,
    statut_commercial: 'en_attente', intention: '', dernier_message: m, dernier_message_at: m.received_at,
    messages_recus: [m], derniere_reponse_afroboost: null, reponse_apres_dernier_message: false, rang: 4,
  }));
  mockEtatParSection = {
    prospects: { etat: 'ok', donnees: { total: 142, returned: 1, limit: 25, offset: 0,
      counts: { total: 142, a_contacter: 83, contacte: 52, repondu: 7 }, prospects: [prospect()] } },
    campagnes: { etat: 'ok', donnees: { total: 0, campaigns: [] } },
    reponses: { etat: 'ok', donnees: { messages: msgs, total: 2, a_rattacher: 0, non_lues: 0, a_repondre: 0,
      appel_a_faire: 0, en_attente: 2, refus: 0, traite: 0, conversations, conversations_total: 2,
      conversations_counts: { total: 2, en_attente: 2 } } },
  };
}

// Compteur de rendus de l'écran (React Profiler) : une boucle le ferait exploser.
let rendus = 0;
let consommations = 0;

// Comme CoachDashboard : la notification pose une cible ET bascule sur Prospection ;
// la cible est EFFACÉE dès que l'écran l'a consommée (setP3Cible('')).
function Cockpit() {
  const [mode, setMode] = useState('clients');
  const [cible, setCible] = useState('');
  const c = useCockpitProspection();
  return (
    <div>
      <button data-testid="mode-clients" onClick={() => setMode('clients')}>Clients</button>
      <button data-testid="mode-prospection" onClick={() => setMode('prospection')}>Prospection</button>
      <button data-testid="notification-dynam" onClick={() => { setCible('m-dyn'); setMode('prospection'); }}>notif</button>
      {mode === 'clients' && <div data-testid="vue-clients">Campagnes clients</div>}
      {mode === 'prospection' && (
        <div>
          <span data-testid="total-barre">{c.total === null ? '' : String(c.total)}</span>
          <button data-testid="sec-prospects" aria-current={!c.messagesOuvert && c.vueActive === 'prospects' ? 'page' : undefined}
                  onClick={() => c.choisir('prospects')}>Prospects</button>
          <button data-testid="sec-conversations" aria-current={!c.messagesOuvert && c.vueActive === 'reponses' ? 'page' : undefined}
                  onClick={() => c.choisir('reponses')}>Conversations partenaires</button>
          <button data-testid="sec-messages" aria-current={c.messagesOuvert ? 'page' : undefined}
                  onClick={() => c.choisir('messages')}>Messages & relances</button>
          {/* V588 — même câblage que CoachDashboard : Messages monté à la 1re ouverture,
              ProspectsSection jamais démonté (masqué). */}
          {c.messagesMonte && (
            <div data-testid="enveloppe-messages" style={{ display: c.messagesOuvert ? 'block' : 'none' }}>
              <MessagesRelancesSection API="/api" />
            </div>
          )}
          <div data-testid="enveloppe-prospects" style={{ display: c.messagesOuvert ? 'none' : 'block' }}>
          <Profiler id="ps" onRender={() => { rendus += 1; }}>
            <ProspectsSection API="/api" inboundCible={cible}
                              onCibleConsommee={() => { consommations += 1; setCible(''); }}
                              ongletPilote={c.vuePilote} onEtat={c.surEtat} onDemandeOnglet={c.demander} />
          </Profiler>
          </div>
        </div>
      )}
    </div>
  );
}

let conteneur = null;
let racine = null;
const par = (id) => conteneur.querySelector(`[data-testid="${id}"]`);
const actives = () => Array.from(conteneur.querySelectorAll('[aria-current="page"]'))
  .map((b) => b.dataset.testid).filter((id) => id && id.indexOf('sec-') === 0);
const vueAffichee = () => (par('file-conversations') || par('reponses-recues') ? 'reponses'
  : (par('tuile-Total') ? 'prospects' : '?'));
async function cliquer(id) { await act(async () => { par(id).click(); }); }

// Stabilité : après la dernière action, plus AUCUN rendu ne doit se produire.
async function stable() {
  const avant = rendus;
  await act(async () => { await new Promise((r) => setTimeout(r, 50)); });
  return rendus - avant;
}

beforeEach(() => { rendus = 0; consommations = 0; donneesTest(); });
afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur) document.body.removeChild(conteneur);
  racine = null; conteneur = null; mockEtatParSection = null;
});

async function monter(element) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  await act(async () => { racine.render(element); });
}

test('aller-retour Clients → Prospection → Prospects → Conversations → Prospects → Clients → Prospection : aucune boucle', async () => {
  await monter(<Cockpit />);
  expect(par('vue-clients')).toBeTruthy();

  await cliquer('mode-prospection');
  expect(await stable()).toBe(0);
  // Rien choisi : choix par défaut de l'écran (des réponses existent → conversations).
  expect(vueAffichee()).toBe('reponses');
  expect(actives()).toEqual(['sec-conversations']);

  await cliquer('sec-prospects');
  expect(await stable()).toBe(0);
  expect(vueAffichee()).toBe('prospects');
  expect(actives()).toEqual(['sec-prospects']);

  await cliquer('sec-conversations');
  expect(await stable()).toBe(0);
  expect(vueAffichee()).toBe('reponses');
  expect(actives()).toEqual(['sec-conversations']);

  await cliquer('sec-prospects');
  expect(await stable()).toBe(0);
  expect(vueAffichee()).toBe('prospects');

  await cliquer('mode-clients');
  expect(par('vue-clients')).toBeTruthy();

  // LE CAS QUI BOUCLAIT EN V587b : remontage avec un choix déjà mémorisé.
  rendus = 0;
  await cliquer('mode-prospection');
  expect(await stable()).toBe(0);
  expect(rendus).toBeLessThan(10);
  expect(vueAffichee()).toBe('prospects');            // le choix mémorisé est respecté
  expect(actives()).toEqual(['sec-prospects']);         // une seule section active
});

test('10 bascules Prospects ↔ Conversations puis 10 Clients ↔ Prospection : état stable, rendus bornés', async () => {
  await monter(<Cockpit />);
  await cliquer('mode-prospection');
  for (let i = 0; i < 10; i += 1) {
    await cliquer(i % 2 ? 'sec-conversations' : 'sec-prospects');
    expect(await stable()).toBe(0);
    expect(vueAffichee()).toBe(i % 2 ? 'reponses' : 'prospects');
    expect(actives().length).toBe(1);
  }
  for (let i = 0; i < 10; i += 1) {
    await cliquer('mode-clients');
    await cliquer('mode-prospection');
    expect(await stable()).toBe(0);
    expect(vueAffichee()).toBe('reponses');            // dernier choix : conversations
    expect(actives()).toEqual(['sec-conversations']);
  }
  expect(rendus).toBeLessThan(400);                     // une boucle en ferait des milliers
});

test('notification ciblée : UNE demande au parent, conversation ouverte, aucune boucle', async () => {
  await monter(<Cockpit />);
  await cliquer('mode-prospection');
  await cliquer('sec-prospects');                       // l'utilisateur est sur la liste…
  expect(vueAffichee()).toBe('prospects');
  // … une notification vise la conversation Dynam (écran déjà monté).
  rendus = 0;
  await cliquer('notification-dynam');
  expect(await stable()).toBe(0);
  expect(rendus).toBeLessThan(15);
  expect(vueAffichee()).toBe('reponses');                // le parent a sélectionné Conversations
  expect(actives()).toEqual(['sec-conversations']);
  expect(conteneur.textContent).toContain('Dynam');
  expect(consommations).toBe(1);                         // consommée une seule fois
  // Ensuite l'utilisateur navigue librement : aucun retour forcé.
  await cliquer('sec-prospects');
  expect(await stable()).toBe(0);
  expect(vueAffichee()).toBe('prospects');
  expect(consommations).toBe(1);
});

test('notification ciblée depuis Clients (remontage) : même résultat, une seule consommation', async () => {
  await monter(<Cockpit />);
  await cliquer('mode-prospection');
  await cliquer('sec-prospects');
  await cliquer('mode-clients');
  rendus = 0;
  await cliquer('notification-dynam');
  expect(await stable()).toBe(0);
  expect(rendus).toBeLessThan(15);
  expect(vueAffichee()).toBe('reponses');
  expect(actives()).toEqual(['sec-conversations']);
  expect(consommations).toBe(1);
});


test('V587d — la barre annonce le total de la PORTÉE (142), pas le nombre filtré (7)', async () => {
  // Liste filtrée sur « Répondu » : 7 lignes, mais 142 prospects dans la portée.
  mockEtatParSection.prospects.donnees = { total: 7, returned: 1, limit: 25, offset: 0,
    counts: { total: 142, a_contacter: 83, contacte: 52, repondu: 7 }, prospects: [prospect()] };
  await monter(<Cockpit />);
  await cliquer('mode-prospection');
  await cliquer('sec-prospects');
  expect(par('total-barre').textContent).toBe('142');
});


test('V588 — Messages & relances : bascules avec Prospects / Conversations, aucun remontage, aucune boucle', async () => {
  await monter(<Cockpit />);
  await cliquer('mode-prospection');
  await cliquer('sec-prospects');
  const ecranProspects = par('enveloppe-prospects').firstChild;
  rendus = 0;
  for (let i = 0; i < 10; i += 1) {
    await cliquer('sec-messages');
    expect(await stable()).toBe(0);
    expect(actives()).toEqual(['sec-messages']);
    expect(par('enveloppe-messages').style.display).toBe('block');
    expect(par('enveloppe-prospects').style.display).toBe('none');
    expect(par('messages-relances')).toBeTruthy();
    await cliquer(i % 2 ? 'sec-conversations' : 'sec-prospects');
    expect(await stable()).toBe(0);
    expect(actives()).toEqual([i % 2 ? 'sec-conversations' : 'sec-prospects']);
    expect(par('enveloppe-messages').style.display).toBe('none');
    expect(vueAffichee()).toBe(i % 2 ? 'reponses' : 'prospects');
  }
  // ProspectsSection n'a jamais été démonté : même nœud DOM qu'au départ.
  expect(par('enveloppe-prospects').firstChild).toBe(ecranProspects);
  expect(rendus).toBeLessThan(200);
});

test('V588 — une notification ciblée pendant Messages & relances ramène sur la conversation', async () => {
  await monter(<Cockpit />);
  await cliquer('mode-prospection');
  await cliquer('sec-messages');
  expect(actives()).toEqual(['sec-messages']);
  await cliquer('notification-dynam');
  expect(await stable()).toBe(0);
  expect(actives()).toEqual(['sec-conversations']);
  expect(par('enveloppe-messages').style.display).toBe('none');
  expect(vueAffichee()).toBe('reponses');
  expect(consommations).toBe(1);
});

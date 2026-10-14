// V619 — le fil complet d'une conversation partenaire : projection serveur `messages_fil`
// (J0 → J+14, réponses manuelles = `approved_text`, messages reçus sans seconde découpe).
import React from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import FilConversation, { estLong } from '../FilConversation';
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

const LONG = `Bonjour,\n${'Ligne longue du partenaire. '.repeat(40)}\nFIN DU TEXTE LONG`;
const CITE = 'Le mer. 14 oct. 2026, Afroboost a écrit :\n> Bonjour';
const FIL = [
  { id: 'a:j0', direction: 'outgoing', type: 'j0', date: '2026-10-11T08:00:00+00:00',
    subject: 'Afroboost à Paris', text: 'Bonjour,\nJe suis Coach Bassi.', texte_garanti: true, remise: 'remis' },
  { id: 'a:j3', direction: 'outgoing', type: 'j3', date: '2026-10-14T07:00:00+00:00',
    subject: 'Petite relance', text: 'Je me permets de relancer.', texte_garanti: true, remise: 'remis' },
  { id: 'in-1', direction: 'incoming', type: 'partner_reply', date: '2026-10-14T12:08:58.912Z',
    subject: 'Re: Afroboost à Paris', text: 'Bonjour BASSI,\nOui tout à fait.', quoted: CITE, texte_garanti: true },
  { id: 'rep-1', direction: 'outgoing', type: 'manual_reply', date: '2026-10-14T14:27:36+00:00',
    subject: 'Re: Afroboost à Paris', text: 'Bonjour Ludivine,\nMerci beaucoup.', texte_garanti: true, remise: 'remis' },
  { id: 'in-2', direction: 'incoming', type: 'partner_reply', date: '2026-10-14T14:50:03Z',
    subject: 'Re: Afroboost à Paris', text: LONG, quoted: '', texte_garanti: true },
  { id: 'a:j7', direction: 'outgoing', type: 'j7', date: '2026-10-18T07:00:00+00:00',
    subject: 'Dernière idée', text: 'Une dernière idée.', texte_garanti: true, remise: 'rebond' },
  { id: 'a:j14', direction: 'outgoing', type: 'j14', date: '2026-10-25T07:00:00+00:00',
    subject: 'Je clos mon suivi', text: 'Je clos mon suivi.', texte_garanti: true, remise: 'en_attente' },
];

let conteneur; let racine;
const tous = (id, base) => Array.from((base || conteneur).querySelectorAll(`[data-testid="${id}"]`));
const attendre = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });
async function cliquer(el) { await act(async () => { el.click(); }); await attendre(); await attendre(); }

function monter(element) {
  conteneur = document.createElement('div');
  document.body.appendChild(conteneur);
  racine = createRoot(conteneur);
  return act(async () => { racine.render(element); });
}
afterEach(async () => {
  if (racine) await act(async () => { racine.unmount(); });
  if (conteneur && conteneur.parentNode) conteneur.parentNode.removeChild(conteneur);
  racine = null; conteneur = null;
  jest.restoreAllMocks();
  jest.clearAllMocks();
});

describe('FilConversation', () => {
  test('tous les messages, dans l’ordre reçu du serveur, avec ENVOYÉ / REÇU et le type', async () => {
    await monter(<FilConversation fil={FIL} />);
    const el = tous('fil-message');
    expect(el).toHaveLength(7);
    expect(el.map((e) => e.dataset.type)).toEqual(['j0', 'j3', 'partner_reply', 'manual_reply', 'partner_reply', 'j7', 'j14']);
    expect(el.map((e) => e.dataset.direction)).toEqual(
      ['outgoing', 'outgoing', 'incoming', 'outgoing', 'incoming', 'outgoing', 'outgoing']);
    const types = tous('fil-type').map((t) => t.textContent);
    expect(types).toEqual(['Message J0', 'Relance J+3', 'Réponse du partenaire', 'Réponse manuelle',
      'Réponse du partenaire', 'Relance J+7', 'Relance J+14']);
    expect(el[3].textContent).toContain('ENVOYÉ');
    expect(el[2].textContent).toContain('REÇU');
  });

  test('réponse manuelle : texte intégral, objet, « Remis » ; date et heure dans l’en-tête', async () => {
    await monter(<FilConversation fil={FIL} />);
    const rep = tous('fil-message')[3];
    expect(rep.querySelector('[data-testid="fil-texte"]').textContent).toBe('Bonjour Ludivine,\nMerci beaucoup.');
    expect(rep.querySelector('[data-testid="fil-objet"]').textContent).toBe('Re: Afroboost à Paris');
    expect(rep.querySelector('[data-testid="fil-remise"]').textContent).toBe('Remis');
    expect(rep.querySelector('[data-testid="fil-entete"]').textContent).toMatch(/14\/10 à \d\d:\d\d/);
    expect(rep.querySelector('svg')).toBeTruthy();   // icône SVG, jamais un emoji
  });

  test('statuts de remise : remis, rebond, en attente', async () => {
    await monter(<FilConversation fil={FIL} />);
    const remises = tous('fil-remise').map((r) => r.dataset.remise);
    expect(remises).toEqual(['remis', 'remis', 'remis', 'rebond', 'en_attente']);
    expect(tous('fil-remise').map((r) => r.textContent)).toEqual(['Remis', 'Remis', 'Remis', 'Rebond', 'En attente']);
  });

  test('message reçu : texte principal SANS la citation ; citation repliée à part', async () => {
    await monter(<FilConversation fil={FIL} />);
    const recu = tous('fil-message')[2];
    expect(recu.querySelector('[data-testid="fil-texte"]').textContent).toBe('Bonjour BASSI,\nOui tout à fait.');
    const cite = recu.querySelector('[data-testid="fil-cite"]');
    expect(cite).toBeTruthy();
    expect(cite.open).toBe(false);
    expect(cite.querySelector('summary').textContent).toBe('Voir le message cité');
    expect(cite.textContent).toContain('Afroboost a écrit');
    expect(tous('fil-message')[4].querySelector('[data-testid="fil-cite"]')).toBeNull();
  });

  test('message long : replié, « Voir plus » puis « Voir moins », texte intégral toujours présent', async () => {
    await monter(<FilConversation fil={FIL} />);
    expect(estLong(LONG)).toBe(true);
    expect(estLong('court')).toBe(false);
    const long = tous('fil-message')[4];
    const corps = long.querySelector('[data-testid="fil-texte"]');
    expect(corps.textContent).toContain('FIN DU TEXTE LONG');
    expect(corps.style.overflow).toBe('hidden');
    const bouton = long.querySelector('[data-testid="fil-voir-plus"]');
    expect(bouton.textContent).toBe('Voir plus');
    await cliquer(bouton);
    expect(long.querySelector('[data-testid="fil-texte"]').style.overflow).toBe('');
    expect(long.querySelector('[data-testid="fil-voir-plus"]').textContent).toBe('Voir moins');
    await cliquer(long.querySelector('[data-testid="fil-voir-plus"]'));
    expect(long.querySelector('[data-testid="fil-voir-plus"]').textContent).toBe('Voir plus');
    expect(tous('fil-message')[3].querySelector('[data-testid="fil-voir-plus"]')).toBeNull();
  });

  test('texte non prouvé : « Texte historique non garanti », aucun texte inventé', async () => {
    await monter(<FilConversation fil={[{ id: 'v:j0', direction: 'outgoing', type: 'j0',
      date: '2026-09-03T12:00:00Z', subject: '', text: null, texte_garanti: false, remise: 'inconnu' }]} />);
    expect(tous('fil-texte')).toHaveLength(0);
    expect(tous('fil-sans-texte')[0].textContent).toBe('Texte historique non garanti');
    expect(tous('fil-remise')[0].textContent).toBe('Remise non suivie');
  });

  test('fil vide ou absent : rien n’est rendu', async () => {
    await monter(<FilConversation fil={undefined} />);
    expect(tous('fil-conversation')).toHaveLength(0);
  });
});

describe('Messages & relances — le fil V619 remplace la reconstruction locale', () => {
  const CAMPAGNE = { id: 'c1', nom: 'GV', etat: 'approuvee', subject_j0: 'Objet J0', subject_j3: 'Objet J3',
    subject_j7: 'Objet J7', subject_j14: 'Objet J14' };
  const ACTION = { id: 'a-m', recipient_key: 'TEST-M', organisations: ['Centre Test'], prospect_ids: ['TEST-M'],
    channel: 'email', execution_type: 'AUTO', statut: 'envoye', target: 'm@exemple.test',
    message_j0: 'J0 APPROUVÉ', message_j3: 'J3 APPROUVÉ', message_j7: 'J7 APPROUVÉ', message_j14: 'J14 APPROUVÉ',
    sent_at: '2026-10-11T08:00:00+00:00', provider_status: 'delivered',
    j3_sent_at: '2026-10-14T07:00:00+00:00', j3_provider_status: 'delivered',
    j7_sent_at: '2026-10-18T07:00:00+00:00', j7_provider_status: 'bounced',
    j14_sent_at: '2026-10-25T07:00:00+00:00', j14_provider_status: 'accepted',
    replied_at: '2026-10-14T12:08:58Z' };
  const RECU = { id: 'in-1', received_at: '2026-10-14T12:08:58.912Z', subject: 'Re: Objet J0', from_email: 'm@exemple.test',
    body_text: 'Bonjour BASSI,\nOui tout à fait.', body_quoted: CITE, read_at: '2026-10-14T13:00:00Z' };
  const CONV = { action_id: 'a-m', organisation: 'Centre Test', nb_messages: 1, message_ids: ['in-1'],
    messages_recus: [RECU], dernier_message: RECU, non_lues: 0, statut_commercial: 'en_attente',
    derniere_reponse_afroboost: { sent_at: '2026-10-14T14:27:36+00:00', objet: 'Re: Objet J0' },
    reponse_apres_dernier_message: true, messages_fil: FIL };

  function serveur(url) {
    if (url === '/api/prospect-campaigns') return { campaigns: [CAMPAGNE] };
    if (url === '/api/prospect-campaigns/c1') return { campaign: CAMPAGNE, actions: [ACTION] };
    if (url === '/api/prospect-inbound') return { conversations: [CONV], messages: [] };
    if (url === '/api/partner-prospects') return { total: 0, prospects: [] };
    if (url === '/api/feature-flags') return {};
    if (/\/notes$/.test(url)) return { notes: [] };
    if (/\/brouillon$/.test(url)) {
      return { brouillon: { reponse_proposee: 'BROUILLON COURANT NE DOIT PAS SERVIR DE PREUVE', updated_at: '2026-10-14T10:00:00Z' } };
    }
    throw new Error(`URL inattendue ${url}`);
  }

  test('le panneau montre le fil serveur : approved_text, J+14, texte reçu intact, jamais le brouillon', async () => {
    jest.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-10-26T14:00:00Z'));
    axios.get.mockImplementation((url) => Promise.resolve({ data: serveur(url) }));
    await monter(<MessagesRelancesSection API="/api" />);
    await attendre(); await attendre();
    const ligne = tous('mr-ligne').find((l) => l.textContent.includes('Centre Test'));
    await cliquer(ligne.querySelector('[data-testid="mr-ligne-entete"]'));
    const panneau = document.body.querySelector('[data-testid="mr-panneau"]');
    expect(panneau).toBeTruthy();
    const fil = tous('fil-message', panneau);
    expect(fil.map((e) => e.dataset.type)).toEqual(['j0', 'j3', 'partner_reply', 'manual_reply', 'partner_reply', 'j7', 'j14']);
    const texte = panneau.textContent;
    expect(texte).toContain('Bonjour Ludivine,\nMerci beaucoup.');
    expect(texte).toContain('Relance J+14');
    expect(texte).not.toContain('BROUILLON COURANT NE DOIT PAS SERVIR DE PREUVE');
    expect(texte).not.toContain('(message sans texte)');
    expect(tous('mr-bulle-partenaire', panneau)).toHaveLength(0);   // plus de reconstruction locale
    expect(panneau.querySelector('[data-testid="mr-etape-j14"]')).toBeTruthy();
  });

  test('sans fil serveur (repli) : le texte reçu n’est plus recoupé au frontend', async () => {
    jest.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-10-26T14:00:00Z'));
    const sansFil = { ...CONV, messages_fil: undefined,
      messages_recus: [{ ...RECU, body_text: 'De: quelqu’un\nTexte réel conservé par le serveur' }] };
    axios.get.mockImplementation((url) => Promise.resolve({ data: url === '/api/prospect-inbound'
      ? { conversations: [sansFil], messages: [] } : serveur(url) }));
    await monter(<MessagesRelancesSection API="/api" />);
    await attendre(); await attendre();
    const ligne = tous('mr-ligne').find((l) => l.textContent.includes('Centre Test'));
    await cliquer(ligne.querySelector('[data-testid="mr-ligne-entete"]'));
    const panneau = document.body.querySelector('[data-testid="mr-panneau"]');
    const bulle = tous('mr-bulle-partenaire', panneau)[0];
    expect(bulle.textContent).toContain('Texte réel conservé par le serveur');
    expect(bulle.textContent).not.toContain('(message sans texte)');
    expect(tous('mr-bulle-afroboost', panneau).some((b) => b.textContent.includes('Relance J+14'))).toBe(true);
  });
});

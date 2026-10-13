/**
 * V618M — avantages membres réglés par le coach (offre par offre) + urgence / capacité séparées.
 * Le PRIX est décidé par le serveur ; ici : l'éditeur, l'espace membre, la page publique.
 */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), put: jest.fn(), create: jest.fn(), interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } } }));
jest.mock('../coach/InvitationMiniature', () => function Mini() { return null; });
// eslint-disable-next-line import/first
import axios from 'axios';
// eslint-disable-next-line import/first
import EditeurInvitation from '../coach/EditeurInvitation';
// eslint-disable-next-line import/first
import EvenementsOfferts, { CarteEvenement, evtDeLOccurrence } from '../EvenementsOfferts';
// eslint-disable-next-line import/first
import InvitationPublique from '../InvitationPublique';
// eslint-disable-next-line import/first
import { changementsAvantages, erreurAvantages, prixMembreApercu, regleEnvoyee, formAvantages } from '../../utils/avantagesMembres';
// eslint-disable-next-line import/first
import { retenirIntentionMembre } from '../../utils/participationEvenement';

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
// V618M : la carte événement lit les conditions publiées AU MOMENT de réserver (aucune ici).
beforeEach(() => { axios.get.mockResolvedValue({ data: { required: false } }); });
let conteneur = null; let racine = null;
function rendre(el) { conteneur = document.createElement('div'); document.body.appendChild(conteneur); racine = createRoot(conteneur); racine.render(el); }
afterEach(() => { if (racine) act(() => racine.unmount()); if (conteneur) conteneur.remove(); racine = null; conteneur = null; jest.clearAllMocks(); delete global.fetch; window.localStorage.clear(); });
const q = (id) => document.querySelector(`[data-testid="${id}"]`);
const json = (corps, ok = true, status = 200) => Promise.resolve({ ok, status, json: () => Promise.resolve(corps) });
async function attendre(fn) { let e; for (let i = 0; i < 40; i += 1) { try { fn(); return; } catch (x) { e = x; } await act(async () => { await new Promise((r) => setTimeout(r, 25)); }); } throw e; }
function saisir(el, valeur) {
  const proto = el.tagName === 'SELECT' ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, valeur);
  el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
}

const EVT = { date: '2026-10-28', heure: '18:45', lieu: 'Valangines, 2000 Neuchâtel', date_modifiable: true,
  tarifs: { prevente: 25, standard: 30, derniere_minute: 40, libelles: { prevente: 'Prévente', standard: 'Standard', derniere_minute: 'Dernière minute' },
    fin_prevente: '2026-10-21T18:45', fin_standard: '2026-10-27T18:45', debut_evenement: '2026-10-28T18:45', prix_actif: 30, palier_actif: 'standard' },
  membres: { configuree: true, actif: true, libelle: 'Avantages membres' }, participants: { reservations: 0, paiements: 0 },
  avantages: { actif: true, regles: [{ offer_id: 'OFF-8M', nom: 'Membres — 8 mois', type: 'gratuit', valeur: null, active: true }],
    offres: [{ id: 'OFF-8M', nom: 'Membres — 8 mois' }, { id: 'OFF-ETU', nom: 'Étudiant' }, { id: 'OFF-PULSE', nom: 'Pulse X10' }],
    autres: [{ id: 'OFF-OLD', nom: 'Ancienne offre' }] },
  urgence: { texte: '50 PLACES', visible: false, capacite_limitee: false, capacite_max: null, places_prises: 3 } };
const INV = { id: 'C1', type: 'event_paid', status: 'active', title: 'AFROBOOST SILENT', subtitle: '', description: null, message: null,
  cta_label: '', image_url: null, image_source: 'default', video_url: null, audio_url: null, audio_partage_url: null,
  share_url: 'https://afroboost.com/i/TOK', share_token: 'TOK', version: 3, inviter_display: { prenom: 'Bassi' },
  date_label: 'mercredi 28 octobre', time_label: '18:45', lieu: EVT.lieu, gratuit_membres: true,
  prix_actif: { prix: 30, palier: 'standard', libelle: 'Standard', paliers: [] } };

describe('V618M — règles (écran)', () => {
  test('aperçu du prix membre : gratuit, -20 %, prix fixe, aucun', () => {
    expect(prixMembreApercu({ type: 'gratuit' }, 30)).toBe(0);
    expect(prixMembreApercu({ type: 'reduction', valeur: '20' }, 30)).toBe(24);
    expect(prixMembreApercu({ type: 'prix_fixe', valeur: '20' }, 30)).toBe(20);
    expect(prixMembreApercu({ type: 'prix_fixe', valeur: '50' }, 30)).toBe(30);   // jamais au-dessus du public
  });
  test('envoi : identifiant réel + type + valeur ; « aucun » omis', () => {
    expect(regleEnvoyee({ offer_id: 'X', type: 'reduction', valeur: '20' })).toEqual({ offer_id: 'X', type: 'reduction', valeur: 20 });
    expect(regleEnvoyee({ offer_id: 'X', type: 'prix_fixe', valeur: '19,5' })).toEqual({ offer_id: 'X', type: 'prix_fixe', valeur: 19.5 });
    expect(regleEnvoyee({ offer_id: 'X', type: 'aucun' })).toBeNull();
  });
  test('contrôles : % de 1 à 100, prix fixe obligatoire, capacité entière', () => {
    const f = formAvantages(EVT);
    expect(erreurAvantages(f)).toBe('');
    expect(erreurAvantages(Object.assign({}, f, { avantages: [{ offer_id: 'A', nom: 'Étudiant', type: 'reduction', valeur: '120' }] }))).toMatch(/entre 1 et 100/);
    expect(erreurAvantages(Object.assign({}, f, { avantages: [{ offer_id: 'A', nom: 'Pulse', type: 'prix_fixe', valeur: '' }] }))).toMatch(/prix membre/);
    expect(erreurAvantages(Object.assign({}, f, { urgence: { texte: '', capacite_limitee: true, capacite_max: '0' } }))).toMatch(/capacité/);
  });
  test('aucun changement -> rien à envoyer ; texte + capacité -> `urgence` seulement', () => {
    const f = formAvantages(EVT);
    expect(changementsAvantages(f, EVT)).toEqual({});
    const g = Object.assign({}, f, { urgence: { texte: 'ÉDITION LIMITÉE', visible: true, capacite_limitee: true, capacite_max: '50' } });
    expect(changementsAvantages(g, EVT)).toEqual({ urgence: { texte: 'ÉDITION LIMITÉE', visible: true, capacite_limitee: true, capacite_max: 50 } });
  });
});

describe('V618M — éditeur coach', () => {
  beforeEach(() => {
    axios.get.mockImplementation((url) => (String(url).includes('campaigns-edition')
      ? Promise.resolve({ data: { invitation: INV, evenement: EVT } }) : Promise.resolve({ data: { items: [] } })));
  });

  test('ajouter « Étudiant » à -20 % et « Pulse X10 » à 20 CHF -> PUT avec les VRAIS identifiants ; aperçu du prix', async () => {
    axios.put.mockResolvedValue({ data: {} });
    await act(async () => { rendre(<EditeurInvitation invitationId="C1" onClose={() => {}} />); });
    await attendre(() => expect(q('ed-titre')).toBeTruthy());
    await act(async () => { q('edit-section-avantages-titre').click(); });
    expect(q('ed-avantage-OFF-8M').textContent).toMatch(/Membres — 8 mois/);
    // l'ancienne offre n'est PAS dans la liste principale
    expect([...q('ed-avantage-ajout').querySelectorAll('option')].map((o) => o.value)).toEqual(['', 'OFF-ETU', 'OFF-PULSE']);
    await act(async () => { saisir(q('ed-avantage-ajout'), 'OFF-ETU'); });
    await act(async () => { saisir(q('ed-avantage-type-OFF-ETU'), 'reduction'); });
    await act(async () => { saisir(q('ed-avantage-valeur-OFF-ETU'), '20'); });
    expect(q('ed-avantage-apercu-OFF-ETU').textContent).toBe("Aujourd'hui : 24 CHF au lieu de 30 CHF");
    await act(async () => { saisir(q('ed-avantage-ajout'), 'OFF-PULSE'); });
    await act(async () => { saisir(q('ed-avantage-type-OFF-PULSE'), 'prix_fixe'); });
    await act(async () => { saisir(q('ed-avantage-valeur-OFF-PULSE'), '20'); });
    await act(async () => { q('ed-enregistrer').click(); });
    await attendre(() => expect(axios.put).toHaveBeenCalled());
    const [url, corps] = axios.put.mock.calls.find(([u, c]) => String(u).includes('/evenement') && c && !c.simuler);
    expect(url).toMatch(/campaigns-edition\/C1\/evenement$/);
    expect(corps.avantages_membres).toEqual([{ offer_id: 'OFF-8M', type: 'gratuit' }, { offer_id: 'OFF-ETU', type: 'reduction', valeur: 20 },
      { offer_id: 'OFF-PULSE', type: 'prix_fixe', valeur: 20 }]);
    expect(corps.confirmer).toBeUndefined();
  });

  test('offres masquées / expirées : seulement sur demande ; retirer une offre', async () => {
    await act(async () => { rendre(<EditeurInvitation invitationId="C1" onClose={() => {}} />); });
    await attendre(() => expect(q('ed-titre')).toBeTruthy());
    await act(async () => { q('edit-section-avantages-titre').click(); });
    await act(async () => { q('ed-avantage-autres').click(); });
    expect([...q('ed-avantage-ajout').querySelectorAll('option')].map((o) => o.value)).toContain('OFF-OLD');
    await act(async () => { q('ed-avantage-retirer-OFF-8M').click(); });
    expect(q('ed-avantage-OFF-8M')).toBeNull();
    expect(q('ed-avantages-vide').textContent).toMatch(/tarif public/);
  });

  test('urgence : texte affiché / masqué, capacité séparée ; l’aperçu suit tout de suite', async () => {
    axios.put.mockResolvedValue({ data: {} });
    await act(async () => { rendre(<EditeurInvitation invitationId="C1" onClose={() => {}} />); });
    await attendre(() => expect(q('ed-titre')).toBeTruthy());
    await act(async () => { q('edit-section-urgence-titre').click(); });
    expect(q('ed-urgence-texte').value).toBe('50 PLACES');
    expect(q('ed-urgence').textContent).toMatch(/ne limite jamais les réservations/);
    await act(async () => { q('ed-urgence-visible').click(); });
    await act(async () => { q('ed-capacite-case').click(); });
    await act(async () => { saisir(q('ed-capacite-max'), '50'); });
    expect(q('ed-urgence').textContent).toMatch(/3 places déjà réservées/);
    await act(async () => { q('ed-enregistrer').click(); });
    await attendre(() => expect(axios.put.mock.calls.some(([u, c]) => String(u).includes('/evenement') && c && c.urgence)).toBe(true));
    const [, corps] = axios.put.mock.calls.find(([u, c]) => String(u).includes('/evenement') && c && c.urgence);
    expect(corps.urgence).toEqual({ visible: true, capacite_limitee: true, capacite_max: 50 });
  });
});

describe('V618M — espace membre', () => {
  const BASE = { offer_id: 'EVT', titre: 'AFROBOOST SILENT', datetime: '2026-10-28T18:45:00', lieu: 'Valangines, 2000 Neuchâtel',
    deja_reserve: false, jeton_invitation: 'TOKEVT12345678901', complet: false };
  test('réduction : « -20 % · 30 CHF → 24 CHF » -> [Réserver à 24 CHF] -> Stripe avec l’identité de l’ESPACE (jamais le prix du navigateur)', async () => {
    const appels = [];
    global.fetch = jest.fn((url, opt) => { appels.push([String(url), opt]); return json({ url: 'https://checkout.stripe.com/c/pay/cs_test_m' }); });
    const lieu = window.location;
    delete window.location; window.location = { href: 'https://afroboost.com/espace/AFR-B', origin: 'https://afroboost.com', search: '' };
    try {
      const E = Object.assign({}, BASE, { avantage: { type: 'reduction', valeur: 20, prix_public: 30, prix_membre: 24 } });
      await act(async () => { rendre(<EvenementsOfferts evenements={[E]} accessCode="AFR-B" memberSlug="" jetonEspace="jeton-espace" />); });
      expect(q('evt-offert-avantage').textContent).toBe('-20 %');                // « Ton avantage membre · -20 % »
      expect(q('evt-offert-calcul').textContent).toBe('30 CHF → 24 CHF');
      expect(q('evt-offert-reserver').textContent).toBe('Réserver à 24 CHF');
      await act(async () => { q('evt-offert-reserver').click(); });
      await attendre(() => expect(window.location.href).toBe('https://checkout.stripe.com/c/pay/cs_test_m'));
      const [u, opt] = appels.find(([x]) => x.includes('/api/create-checkout-session'));
      expect(u).toMatch(/create-checkout-session$/);
      expect(opt.headers['x-espace-token']).toBe('jeton-espace');
      const corps = JSON.parse(opt.body);
      expect(corps).toEqual(expect.objectContaining({ offerId: 'EVT', quantity: 1, retourInvitation: true, espace: { code: 'AFR-B', slug: '' } }));
      expect(corps.attribution.invitation).toBe('TOKEVT12345678901');
      expect(axios.post).not.toHaveBeenCalled();                  // jamais la route « offert » pour un tarif payant
    } finally { window.location = lieu; }
  });
  test('prix fixe : « 20 CHF » ; gratuit : « PLACE OFFERTE » -> [Réserver ma place offerte]', async () => {
    const F = Object.assign({}, BASE, { offer_id: 'F', avantage: { type: 'prix_fixe', valeur: 20, prix_public: 30, prix_membre: 20 } });
    const G = Object.assign({}, BASE, { offer_id: 'G', avantage: { type: 'gratuit', valeur: null, prix_public: 30, prix_membre: 0 } });
    await act(async () => { rendre(<EvenementsOfferts evenements={[F, G]} accessCode="AFR-B" memberSlug="" jetonEspace="j" />); });
    const cartes = [...document.querySelectorAll('[data-testid="evt-offert-avantage"]')].map((e) => e.textContent);
    expect(cartes).toEqual(['20 CHF', 'PLACE OFFERTE']);
    const boutons = [...document.querySelectorAll('[data-testid="evt-offert-reserver"]')].map((e) => e.textContent);
    expect(boutons).toEqual(['Réserver à 20 CHF', 'Réserver ma place offerte']);
  });
  test('capacité réelle atteinte : « complet », aucun bouton', async () => {
    const C = Object.assign({}, BASE, { complet: true, avantage: { type: 'gratuit', prix_public: 30, prix_membre: 0 } });
    await act(async () => { rendre(<EvenementsOfferts evenements={[C]} accessCode="AFR-B" memberSlug="" jetonEspace="j" />); });
    expect(q('evt-offert-complet').textContent).toMatch(/complet/);
    expect(q('evt-offert-reserver')).toBeNull();
  });
  test('aucun avantage pour cet abonnement : on le dit, avec le tarif actuel', async () => {
    global.fetch = jest.fn(() => json({ prix_actif: { prix: 30 } }));
    retenirIntentionMembre('EVT-1', 'TOKEVT12345678901');
    await act(async () => { rendre(<EvenementsOfferts evenements={[]} accessCode="AFR-D" memberSlug="" jetonEspace="j" />); });
    await attendre(() => expect(q('evt-offert-tarif-public').textContent).toBe('Tarif actuel : 30 CHF'));
    expect(q('evt-offert-non-eligible').textContent).toMatch(/Ton abonnement ne comprend pas d’avantage pour cet événement\./);
  });
});

describe('V618M — page publique', () => {
  const PUB = { type: 'event_paid', title: 'AFROBOOST SILENT', offer_id: 'EVT', date_label: 'mercredi 28 octobre', time_label: '18:45',
    lieu: 'Valangines', inviter_display: { prenom: 'Bassi' }, gratuit_membres: true, reservation_directe: { offer_id: 'EVT' },
    prix_actif: { prix: 30, palier: 'standard', libelle: 'Standard', paliers: [] } };
  test('« Déjà membre Afroboost ? Voir mon tarif membre » — jamais « 8 mois » écrit en dur', async () => {
    global.fetch = jest.fn(() => json(PUB));
    await act(async () => { rendre(<InvitationPublique token="TOKEVT12345678901" />); });
    await attendre(() => expect(q('inv-pub-membre-compact')).toBeTruthy());
    expect(q('inv-pub-membre-compact').textContent).toMatch(/^Déjà membre Afroboost \?\s*Voir mon tarif membre$/);
    expect(document.body.textContent).not.toMatch(/8 mois/);
  });
  test('texte vide -> aucun badge ; « ÉDITION LIMITÉE » -> badge ; capacité : compteur réel puis « Complet »', async () => {
    global.fetch = jest.fn(() => json(Object.assign({}, PUB, { message_places: null })));
    await act(async () => { rendre(<InvitationPublique token="TOKEVT12345678901" />); });
    await attendre(() => expect(q('inv-pub-cta')).toBeTruthy());
    expect(q('inv-pub-places')).toBeNull();
    act(() => racine.unmount()); conteneur.remove(); racine = null;
    global.fetch = jest.fn(() => json(Object.assign({}, PUB, { message_places: 'ÉDITION LIMITÉE', places_restantes: 4, complet: false })));
    await act(async () => { rendre(<InvitationPublique token="TOKEVT12345678901" />); });
    await attendre(() => expect(q('inv-pub-places').textContent).toMatch(/ÉDITION LIMITÉE/));
    expect(q('inv-pub-places-restantes').textContent).toBe('4 places restantes');
    act(() => racine.unmount()); conteneur.remove(); racine = null;
    global.fetch = jest.fn(() => json(Object.assign({}, PUB, { places_restantes: 0, complet: true })));
    await act(async () => { rendre(<InvitationPublique token="TOKEVT12345678901" />); });
    await attendre(() => expect(q('inv-pub-cta').textContent).toBe('Complet'));
    expect(q('inv-pub-cta').disabled).toBe(true);
  });
});

describe('V618M — agenda de l’espace : réserver depuis la date, sans détour', () => {
  const OCC = { course_id: 'C-EVT', datetime: '2026-10-28T18:45:00', name: 'AFROBOOST SILENT', locationName: 'Valangines, 2000 Neuchâtel',
    offer_id: 'EVT-1', inclus_abonnement: false, lien_evenement: '/i/TOKEVT12345678901', prix_public: 25, complet: false };
  test('date « événement » sans avantage : « Tarif actuel 25 CHF » -> [Réserver à 25 CHF] ; avec avantage : celui du serveur', () => {
    const e = evtDeLOccurrence(OCC, { evenements_offerts: [] });
    expect(e.avantage).toEqual({ type: 'aucun', valeur: null, prix_public: 25, prix_membre: 25 });
    expect(e.jeton_invitation).toBe('TOKEVT12345678901');
    const offert = { offer_id: 'EVT-1', avantage: { type: 'gratuit' } };
    expect(evtDeLOccurrence(OCC, { evenements_offerts: [offert] })).toBe(offert);
  });
  test('conditions demandées AU CLIC, cochées une fois, jamais perdues ; puis réservation gratuite', async () => {
    axios.get.mockResolvedValue({ data: { required: true, version: 'v1', titre: 'Conditions' } });
    axios.post.mockResolvedValue({ data: { success: true, relais: null } });
    let accepte = false;
    const Hote = () => {
      const [ok, setOk] = React.useState(false);
      accepte = ok;
      return <CarteEvenement evt={{ offer_id: 'EVT-1', titre: 'AFROBOOST SILENT', datetime: '2026-10-28T18:45:00', lieu: 'Valangines', avantage: { type: 'gratuit', prix_public: 25, prix_membre: 0 } }}
                             accessCode="AFR-M" memberSlug="" jetonEspace="j" courseId="C-EVT" conditionsAcceptees={ok} onConditions={setOk} />;
    };
    await act(async () => { rendre(<Hote />); });
    expect(q('evt-offert-conditions')).toBeNull();                       // rien avant le clic
    await act(async () => { q('evt-offert-reserver').click(); });
    await attendre(() => expect(q('conditions-participation')).toBeTruthy());
    expect(q('evt-offert-reserver').disabled).toBe(true);
    expect(axios.post).not.toHaveBeenCalled();
    await act(async () => { q('conditions-participation').querySelector('input').click(); });
    expect(accepte).toBe(true);                                           // l'état vit chez le parent (agenda)
    await act(async () => { q('evt-offert-reserver').click(); });
    await attendre(() => expect(axios.post).toHaveBeenCalled());
    expect(String(axios.post.mock.calls[0][0])).toMatch(/\/evenement\/EVT-1\/offert$/);
  });
  test('« Voir les détails » s’ouvre DANS la carte (aucune navigation)', async () => {
    global.fetch = jest.fn(() => json({ description: 'Casque fourni. Tous niveaux.' }));
    const href = window.location.href;
    await act(async () => { rendre(<CarteEvenement evt={evtDeLOccurrence(OCC, {})} accessCode="AFR-M" memberSlug="" jetonEspace="j" courseId="C-EVT" />); });
    expect(q('evt-offert-avantage').textContent).toBe('25 CHF');
    expect(q('evt-offert-reserver').textContent).toBe('Réserver à 25 CHF');
    await act(async () => { q('evt-offert-details').click(); });
    await attendre(() => expect(q('evt-offert-details-contenu').textContent).toMatch(/Casque fourni/));
    expect(window.location.href).toBe(href);
  });
});

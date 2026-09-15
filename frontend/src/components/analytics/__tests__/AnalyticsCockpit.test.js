/**
 * AnalyticsCockpit — ce que l'écran doit garantir :
 *  - UN appel au montage (onglet actif), UN par changement de filtre, AUCUN
 *    sondage périodique (règle CHAT-LOOP) ;
 *  - le mode personnalisé n'appelle pas tant que les deux dates manquent ;
 *  - 401/403 -> message clair, aucun chiffre inventé ;
 *  - les cartes et la couverture de présence affichent EXACTEMENT ce que le
 *    serveur rend (aucune addition côté client), et « inconnue » n'est jamais
 *    présentée comme une absence.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import axios from 'axios';

jest.mock('axios', () => ({ get: jest.fn() }));
// recharts mesure un conteneur : sans layout jsdom, on remplace par des stubs inertes.
jest.mock('recharts', () => {
  const Stub = ({ children }) => <div data-testid="recharts">{children}</div>;
  return { ResponsiveContainer: Stub, LineChart: Stub, BarChart: Stub, Line: () => null, Bar: () => null,
    XAxis: () => null, YAxis: () => null, Tooltip: () => null, CartesianGrid: () => null, Legend: () => null };
});

const AnalyticsCockpit = require('../AnalyticsCockpit').default;
const { parametresRequete, granulariteDe, aujourdhuiISO } = require('../AnalyticsCockpit');

const KPI = {
  periode: { debut: '2026-09-01', fin_exclue: '2026-10-01', granularite: 'jour' },
  perimetre: { coach_id: 'tous', course_id: 'tous' },
  participants: { reservations_cours: 7, uniques: 5, nouveaux: 4, recurrents: 1, sans_email: 1 },
  cours: { seances: 2, moyenne_par_seance: 3.5, autres_jours: 0,
    mercredi: { reservations: 4, seances: 1, moyenne: 4, participants: 4 },
    dimanche: { reservations: 3, seances: 1, moyenne: 3, participants: 3 } },
  reservation: { par_heure: Object.fromEntries([...Array(24)].map((_, h) => [String(h).padStart(2, '0'), 0])),
    par_jour: {}, delai_moyen_jours: 3.4,
    anticipation: { jour_meme: 1, '1_jour': 3, '2_3_jours': 1, '4_7_jours': 1, plus_7_jours: 1, inconnu: 0 } },
  fidelite: { '1': 4, '2_5': 1, '6_10': 0, plus_10: 0 },
  essais: { detectes: 1 },
  presence: { confirmee: 1, absente: 1, inconnue: 5, couverture_pct: 28.6, libelle: '2 vérifiées sur 7 réservations' },
  evolution: [{ periode: '2026-09-09', reservations: 4, participants: 4, essais: 1 }],
  qualite: { presence: 'partiel', valeur_financiere: 'inconnu', valeurs_connues: 0, identite: 'partiel', sans_email: 1, conflits_nom_email: 0 },
  ecartees: { produits: 1, sans_occurrence: 0 },
  requetes: 6,
  cours_disponibles: [{ id: 'c-mer', name: 'Silent', reservations: 6 }, { id: 'c-dim', name: 'Sunday', reservations: 3 }],
};

function monter(props) {
  const div = document.createElement('div');
  document.body.appendChild(div);
  const root = createRoot(div);
  act(() => { root.render(<AnalyticsCockpit {...props} />); });
  return { div, root };
}

beforeEach(() => { axios.get.mockReset(); jest.useRealTimers(); });

describe('helpers purs', () => {
  test('parametresRequete : perso porte du/au, coach et cours seulement si choisis', () => {
    expect(parametresRequete({ periode: 'mois' })).toEqual({ periode: 'mois', granularite: 'jour' });
    expect(parametresRequete({ periode: 'perso', du: '2026-09-01', au: '2026-09-30', coachId: 'c@x', courseId: 'k' }))
      .toEqual({ periode: 'perso', granularite: 'jour', du: '2026-09-01', au: '2026-09-30', coach_id: 'c@x', course_id: 'k' });
  });
  test('granularité : semaine pour l’année, jour sinon', () => {
    expect(granulariteDe('annee')).toBe('semaine');
    expect(granulariteDe('semaine')).toBe('jour');
  });
  test('aujourdhuiISO au format YYYY-MM-DD', () => {
    expect(aujourdhuiISO(new Date(2026, 8, 14))).toBe('2026-09-14');
  });
});

describe('AnalyticsCockpit', () => {
  test('un seul appel au montage, sur /analytics/cockpit, et aucun sondage ensuite', async () => {
    jest.useFakeTimers();
    axios.get.mockResolvedValue({ data: KPI });
    monter({});
    await act(async () => {});
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(axios.get).toHaveBeenCalledWith(expect.stringMatching(/\/analytics\/cockpit$/), { params: { periode: 'mois', granularite: 'jour' } });
    act(() => { jest.advanceTimersByTime(10 * 60 * 1000); });
    expect(axios.get).toHaveBeenCalledTimes(1);
  });

  test('les cartes et la couverture affichent les chiffres du serveur, sans no-show déduit', async () => {
    axios.get.mockResolvedValue({ data: KPI });
    const { div } = monter({});
    await act(async () => {});
    const t = (id) => div.querySelector(`[data-testid="${id}"]`).textContent;
    expect(t('kpi-participants')).toContain('7');
    expect(t('kpi-uniques')).toContain('5');
    expect(t('kpi-nouveaux')).toContain('4');
    expect(t('kpi-essais')).toContain('1');
    expect(t('kpi-seances')).toContain('2');
    expect(t('kpi-moyenne')).toContain('3.5');
    const pres = t('bloc-presence');
    expect(pres).toContain('2 vérifiées sur 7');
    expect(pres).toContain('28,6 %');
    expect(pres).toContain('5 inconnue');
    expect(pres).toContain('jamais comptées comme absences');
    expect(pres).toContain('partiel');   // badge de qualité (texte, uppercase par CSS)
    expect(div.textContent).toContain('1 achat(s) boutique exclu(s)');
  });

  test('changer la période relance UN appel avec la nouvelle période', async () => {
    axios.get.mockResolvedValue({ data: KPI });
    const { div } = monter({});
    await act(async () => {});
    await act(async () => { div.querySelector('[data-testid="periode-annee"]').click(); });
    expect(axios.get).toHaveBeenCalledTimes(2);
    expect(axios.get).toHaveBeenLastCalledWith(expect.any(String), { params: { periode: 'annee', granularite: 'semaine' } });
  });

  test('403 -> message d’accès refusé, aucune carte', async () => {
    axios.get.mockRejectedValue({ response: { status: 403 } });
    const { div } = monter({});
    await act(async () => {});
    expect(div.querySelector('[role="alert"]').textContent).toMatch(/Accès refusé/);
    expect(div.querySelector('[data-testid="kpi-participants"]')).toBeNull();
  });

  test('filtre cours : liste du serveur, un cours précis, changement, retour à tous, combiné coach+période', async () => {
    axios.get.mockResolvedValue({ data: KPI });
    const { div } = monter({ coaches: [{ email: 'c@x.ch', name: 'C' }] });
    await act(async () => {});
    const sel = div.querySelector('[data-testid="filtre-cours"]');
    expect(sel).not.toBeNull();
    expect([...sel.options].map((o) => o.textContent)).toEqual(['Tous les cours', 'Silent (6)', 'Sunday (3)']);
    const choisir = async (el, v) => act(async () => {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(el, v);
      el.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await choisir(sel, 'c-dim');
    expect(axios.get).toHaveBeenLastCalledWith(expect.any(String), { params: { periode: 'mois', granularite: 'jour', course_id: 'c-dim' } });
    await choisir(sel, 'c-mer');
    expect(axios.get).toHaveBeenLastCalledWith(expect.any(String), { params: { periode: 'mois', granularite: 'jour', course_id: 'c-mer' } });
    // La liste reste complète après sélection (elle vient de cours_disponibles, mémorisée).
    expect([...div.querySelector('[data-testid="filtre-cours"]').options].length).toBe(3);
    await choisir(div.querySelector('[data-testid="filtre-cours"]'), '');
    expect(axios.get).toHaveBeenLastCalledWith(expect.any(String), { params: { periode: 'mois', granularite: 'jour' } });
    // Combinaison période + coach + cours.
    await act(async () => { div.querySelector('[data-testid="periode-semaine"]').click(); });
    await choisir(div.querySelector('[data-testid="filtre-coach"]'), 'c@x.ch');
    await choisir(div.querySelector('[data-testid="filtre-cours"]'), 'c-dim');
    expect(axios.get).toHaveBeenLastCalledWith(expect.any(String), { params: { periode: 'semaine', granularite: 'jour', coach_id: 'c@x.ch', course_id: 'c-dim' } });
    expect(axios.get).toHaveBeenCalledTimes(7);   // 1 montage + 6 changements, jamais plus
  });

  test('filtre coach (super-admin) : le coach_id part dans la requête', async () => {
    axios.get.mockResolvedValue({ data: KPI });
    const { div } = monter({ coaches: [{ email: 'c@x.ch', name: 'C' }] });
    await act(async () => {});
    const sel = div.querySelector('[data-testid="filtre-coach"]');
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
      setter.call(sel, 'c@x.ch');
      sel.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(axios.get).toHaveBeenLastCalledWith(expect.any(String), { params: { periode: 'mois', granularite: 'jour', coach_id: 'c@x.ch' } });
  });
});

// ═══ PHASE 2 — revenus / abonnements / essais : affichage pur des chiffres du serveur ═══
const { chf } = require('../AnalyticsCockpit');

const KPI2 = {
  ...KPI,
  revenus: {
    perimetre: 'global période/coach — le filtre cours ne s\'applique pas',
    ca_encaisse: 1979, ca_stripe: 579, ca_manuel: 1400, transactions_payees: 18, gratuits: 16, panier_moyen: 109.94,
    acheteurs_uniques: 16, revenu_par_participant: 123.69,
    declare_non_prouve: { nombre: 16, montant: 2836 }, montant_inconnu: 18,
    en_attente: { nombre: 188, montant_declare: 12402.98 },
    par_moyen: { stripe_indetermine: { nombre: 11, montant: 429 }, twint: { nombre: 5, montant: 1050 }, virement: { nombre: 1, montant: 250 }, especes: { nombre: 1, montant: 250 }, offert: { nombre: 16, montant: 0 }, stripe_card: { nombre: 0, montant: 0 } },
    par_canal: {}, evolution: [{ periode: '2026-03-09', ca: 250, achats: 1 }],
    valeur_par_cours: { perimetre: 'tous les cours — valeur des réservations au tarif figé, jamais additionnée au CA', cours: [{ id: 'c1', name: 'Silent', reservations: 50, valeur: 666.63, valeurs_connues: 31, couverture_pct: 62.0 }], valeur_totale: 666.63, valeurs_connues: 31, reservations: 50, couverture_pct: 62.0 },
    remboursements: 'Remboursements non disponibles historiquement',
    qualite: { montants: 'partiel', moyen_paiement: 'partiel', stripe_moyen_indetermine: 11 },
  },
  abonnements: {
    perimetre: 'global période/coach — le filtre cours ne s\'applique pas',
    actifs: { total: 32, par_categorie: { pulse_x10: 6, abonnement: 1, carte_membre: 0, essai: 10, autre: 15 } },
    nouveaux: { total: 66, par_categorie: { pulse_x10: 15, abonnement: 10, carte_membre: 0, essai: 17, autre: 24 } },
    expires: { total: 11, par_categorie: {} }, expirant_bientot: { jours: 30, total: 16 },
    pulse_x10: { actifs: 6, vendus: 15 }, cartes_membres: { actives: 6, vendues: 2, regularisees: 4, expirees: 0, total: 6 },
    renouvellements: { confirmes: 0, probables: 12, inconnus: 1, kpi_principal: 'confirmes', libelle_probables: 'Renouvellements probables — non comptés dans le KPI principal', avertissement: 'Certains droits probables peuvent provenir de comptes ou codes de test historiques (aucun filtrage par nom, aucune donnée supprimée).' },
    evolution: [{ periode: '2026-09-01', nouveaux: 2, expires: 0, pulse: 0 }], qualite: { renouvellements: 'partiel' },
  },
  essais_funnel: {
    perimetre: 'global', convention: { fenetre: 'aucune' }, accordes: 17, reserves: 6,
    presence: { confirmee: 3, absente: 0, inconnue: 3, couverture_pct: 50.0 },
    convertis_confirmes: 0, convertis_probables: { total: 2, pulse_x10: 1, abonnement: 0, carte_membre: 1, autre: 0 },
    taux: { reservation: 35.3, presence: 50.0, conversion_confirmee: 0.0, conversion_probable: 11.8 },
    delai_conversion_probable_median_jours: 8, qualite: { conversion: 'partiel', presence: 'partiel' },
  },
};

describe('AnalyticsCockpit — phase 2', () => {
  test('chf : mise en forme seulement, jamais de calcul', () => {
    expect(chf(1979)).toBe('1 979,00 CHF');
    expect(chf(12402.98)).toBe('12 402,98 CHF');
    expect(chf(0)).toBe('0,00 CHF');
    expect(chf(null)).toBe('—');
  });

  test('revenus : CA prouvé, panier, revenu/acheteur, pending et non prouvé HORS CA, remboursements explicites', async () => {
    axios.get.mockResolvedValue({ data: KPI2 });
    const { div } = monter({});
    await act(async () => {});
    const t = (id) => div.querySelector(`[data-testid="${id}"]`).textContent;
    expect(t('kpi-ca')).toContain('1 979,00 CHF');
    expect(t('kpi-ca')).toContain('Stripe 579,00 CHF');
    expect(t('kpi-panier')).toContain('109,94 CHF');
    expect(t('kpi-revenu-participant')).toContain('123,69 CHF');
    expect(t('kpi-pending')).toContain('188');
    expect(t('kpi-pending')).toContain('hors CA');
    expect(t('kpi-non-prouve')).toContain('2 836,00 CHF hors CA');
    expect(t('section-revenus')).toContain('Remboursements non disponibles historiquement');
    expect(t('table-valeur-cours')).toContain('jamais additionnée au CA');
    expect(t('table-valeur-cours')).toContain('31/50');
  });

  test('moyens : « Stripe — moyen non déterminé », jamais card/twint comme moyen réel ; moyens à 0 absents', async () => {
    axios.get.mockResolvedValue({ data: KPI2 });
    const { div } = monter({});
    await act(async () => {});
    const m = div.querySelector('[data-testid="bloc-moyens"]').textContent;
    expect(m).toContain('Stripe — moyen non déterminé : 11');
    expect(m).toContain('TWINT (manuel) : 5');
    expect(m).not.toContain('Stripe — carte');
    expect(m).toContain('carte ou TWINT non distingués sur 11');
    expect(m).toContain('partiel');
  });

  test('abonnements : actifs, nouveaux, expirés, Pulse, cartes ; confirmés = KPI principal, probables à part', async () => {
    axios.get.mockResolvedValue({ data: KPI2 });
    const { div } = monter({});
    await act(async () => {});
    const t = (id) => div.querySelector(`[data-testid="${id}"]`).textContent;
    expect(t('kpi-actifs')).toContain('32');
    expect(t('kpi-actifs')).toContain('Pulse X10 6');
    expect(t('kpi-nouveaux-abos')).toContain('66');
    expect(t('kpi-expires')).toContain('11');
    expect(t('kpi-expires')).toContain('16 expirent sous 30 j');
    expect(t('kpi-pulse')).toContain('6');
    expect(t('kpi-pulse')).toContain('15 vendu(s)');
    expect(t('kpi-cartes')).toContain('6');
    expect(t('kpi-cartes')).toContain('2 vendue(s)');
    expect(t('kpi-renouv-confirmes')).toContain('0');
    expect(t('kpi-renouv-probables')).toContain('12');
    expect(t('kpi-renouv-inconnus')).toContain('1');
    expect(t('bloc-renouvellements')).toContain('CONFIRMÉS comptent dans le KPI principal');
    expect(t('kpi-renouv-probables')).toContain('non comptés dans le KPI principal');
    expect(t('note-renouv-test')).toContain('codes de test');
  });

  test('essais : funnel, présence inconnue ≠ absence, conversions par cible, convention sans fenêtre', async () => {
    axios.get.mockResolvedValue({ data: KPI2 });
    const { div } = monter({});
    await act(async () => {});
    const t = (id) => div.querySelector(`[data-testid="${id}"]`).textContent;
    expect(t('funnel-accordes')).toContain('17');
    expect(t('funnel-reserves')).toContain('6');
    expect(t('funnel-presents')).toContain('3');
    expect(t('funnel-confirmes')).toContain('0');
    expect(t('funnel-probables')).toContain('2');
    expect(t('funnel-essais')).toContain('3 inconnue(s)');
    expect(t('funnel-essais')).toContain("n'est jamais une absence");
    expect(t('kpi-conv-tout')).toContain('2');
    expect(t('kpi-conv-pulse')).toContain('1');
    expect(t('kpi-conv-carte')).toContain('1');
    expect(t('bloc-conversion')).toContain('sans fenêtre');
    expect(t('bloc-conversion')).toContain('8 jour(s)');
  });

  test('filtre cours : les sections phase 2 disent « filtre cours NON appliqué », les KPI phase 1 restent', async () => {
    axios.get.mockResolvedValue({ data: KPI2 });
    const { div } = monter({});
    await act(async () => {});
    expect(div.querySelectorAll('[data-testid="perimetre-global"]').length).toBe(3);
    expect(div.querySelector('[data-testid="perimetre-global"]').textContent).toBe('Global période/coach');
    const sel = div.querySelector('[data-testid="filtre-cours"]');
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(sel, 'c-dim');
      sel.dispatchEvent(new Event('change', { bubbles: true }));
    });
    const badges = [...div.querySelectorAll('[data-testid="perimetre-global"]')].map((b) => b.textContent);
    expect(badges).toEqual(Array(3).fill('Global période/coach — filtre cours NON appliqué'));
    expect(div.querySelector('[data-testid="kpi-participants"]')).not.toBeNull();
    expect(axios.get).toHaveBeenCalledTimes(2);   // toujours un appel par changement, pas plus
  });

  test('sans sections phase 2 dans la réponse : la phase 1 s\'affiche seule, sans erreur', async () => {
    axios.get.mockResolvedValue({ data: KPI });
    const { div } = monter({});
    await act(async () => {});
    expect(div.querySelector('[data-testid="section-revenus"]')).toBeNull();
    expect(div.querySelector('[data-testid="kpi-participants"]')).not.toBeNull();
  });
});

// ═══ TRACKING 2B — ACQUISITION PAR SOURCE ═══
describe('acquisition — par source', () => {
  const SOURCES = {
    convention: 'Source = première touche connue de la personne (attribution.first, M2-A) ; mêmes règles que le cockpit.',
    couverture: { participants_attribues: 3, participants_total: 4, achats_attribues: 3, achats_total: 4 },
    lignes: [
      { cle: 'instagram', source: 'instagram', content: '', libelle: 'instagram', partenaire: false, participants: 2, reservations: 2, essais: 2, essais_reserves: 2,
        presences_confirmees: 1, presence_essais: { confirmee: 1, absente: 0, inconnue: 1 }, achats: 2, clients: 2, convertis_confirmes: 1, convertis_probables: 2,
        taux_conversion_confirmee: 50.0, taux_conversion_probable: 100.0, ca_prouve: 1098, panier_moyen: 549, declare_non_prouve: { nombre: 0, montant: 0 },
        offres: [['Saison hiver — 8 mois', 2]], renouvellements: { confirmes: 1, probables: 0 }, qualite: { conversion: 'partiel', presence: 'partiel', renouvellements: 'fiable' } },
      { cle: 'partenaire:restaurant-x', source: 'partenaire', content: 'restaurant-x', libelle: 'Partenaire — restaurant-x', partenaire: true, participants: 1, reservations: 1, essais: 1, essais_reserves: 1,
        presences_confirmees: 1, presence_essais: { confirmee: 1, absente: 0, inconnue: 0 }, achats: 1, clients: 1, convertis_confirmes: 0, convertis_probables: 1,
        taux_conversion_confirmee: 0.0, taux_conversion_probable: 100.0, ca_prouve: 549, panier_moyen: 549, declare_non_prouve: { nombre: 0, montant: 0 },
        offres: [['Saison hiver — 8 mois', 1]], renouvellements: { confirmes: 0, probables: 0 }, qualite: { conversion: 'partiel', presence: 'fiable', renouvellements: 'inconnu' } },
      { cle: 'inconnue', source: 'inconnue', content: '', libelle: 'inconnue', partenaire: false, participants: 1, reservations: 0, essais: 0, essais_reserves: 0,
        presences_confirmees: 0, presence_essais: { confirmee: 0, absente: 0, inconnue: 0 }, achats: 1, clients: 1, convertis_confirmes: 0, convertis_probables: 0,
        taux_conversion_confirmee: null, taux_conversion_probable: null, ca_prouve: 549, panier_moyen: 549, declare_non_prouve: { nombre: 0, montant: 0 },
        offres: [['Saison hiver — 8 mois', 1]], renouvellements: { confirmes: 0, probables: 0 }, qualite: { conversion: 'inconnu', presence: 'inconnu', renouvellements: 'inconnu' } },
    ],
  };

  test('une ligne par source, partenaire nommé, présence jamais déduite, CA prouvé, renouvellements confirmés à part, aucun CAC', async () => {
    axios.get.mockResolvedValue({ data: { ...KPI, sources: SOURCES } });
    const { div } = monter({});
    await act(async () => {});
    const section = div.querySelector('[data-testid="section-sources"]');
    expect(section).not.toBeNull();
    expect(section.textContent).toMatch(/Acquisition — par source/);
    const ig = div.querySelector('[data-testid="source-instagram"]').textContent;
    expect(ig).toMatch(/instagram/);
    expect(ig).toMatch(/1 098,00 CHF/);    // CA prouvé (format chf)
    expect(ig).toMatch(/50 %/);            // essai → client confirmé
    expect(ig).toMatch(/Saison hiver — 8 mois ×2/);
    const pa = div.querySelector('[data-testid="source-partenaire:restaurant-x"]').textContent;
    expect(pa).toMatch(/Partenaire — restaurant-x/);
    expect(pa).toMatch(/549/);
    const inc = div.querySelector('[data-testid="source-inconnue"]').textContent;
    expect(inc).toMatch(/inconnue/);
    expect(inc).toMatch(/—/);               // pas de taux sans essai
    expect(section.textContent).not.toMatch(/CAC|coût d'acquisition : 0/i);
    expect(section.textContent).toMatch(/3\/4 participants et 3\/4 achats/);
    // L'ordre du serveur est respecté : inconnue en dernier.
    const ordre = [...div.querySelectorAll('[data-testid^="source-"]')].map((r) => r.getAttribute('data-testid'));
    expect(ordre[ordre.length - 1]).toBe('source-inconnue');
  });

  test('sans origine enregistrée : message sobre, pas de tableau', async () => {
    axios.get.mockResolvedValue({ data: { ...KPI, sources: { convention: 'x', lignes: [], couverture: {} } } });
    const { div } = monter({});
    await act(async () => {});
    expect(div.querySelector('[data-testid="section-sources"]').textContent).toMatch(/Aucune origine enregistrée/);
  });

  test('campagnes (dernière touche) : le bloc liste utm_campaign avec achats/acheteurs/CA, à côté des sources first', async () => {
    const campagnes = { convention: 'Dernière touche (attribution.last).', lignes: [
      { source: 'email', medium: 'reactivation', campaign: 'hiver2026', content: 'essai_non_converti', achats: 2, acheteurs: 2, ca_prouve: 78, libelle: 'email / reactivation / hiver2026 / essai_non_converti' },
    ] };
    axios.get.mockResolvedValue({ data: { ...KPI, sources: { ...SOURCES, campagnes } } });
    const { div } = monter({});
    await act(async () => {});
    const bloc = div.querySelector('[data-testid="tableau-campagnes"]');
    expect(bloc).not.toBeNull();
    expect(bloc.textContent).toMatch(/Campagnes — dernière touche/);
    const ligne = div.querySelector('[data-testid="campagne-hiver2026"]').textContent;
    expect(ligne).toMatch(/email \/ reactivation \/ hiver2026 \/ essai_non_converti/);
    expect(ligne).toMatch(/78,00 CHF/);
    // La table des sources (first) est intacte à côté.
    expect(div.querySelector('[data-testid="source-instagram"]')).not.toBeNull();
  });

  test('sans bloc campagnes (ancien serveur) : message sobre, aucune erreur', async () => {
    axios.get.mockResolvedValue({ data: { ...KPI, sources: SOURCES } });
    const { div } = monter({});
    await act(async () => {});
    expect(div.querySelector('[data-testid="tableau-campagnes"]').textContent).toMatch(/Aucun achat attribué à une campagne/);
  });

  test('cockpit sans `sources` (ancien serveur) : la section n’apparaît pas, rien ne casse', async () => {
    axios.get.mockResolvedValue({ data: KPI });
    const { div } = monter({});
    await act(async () => {});
    expect(div.querySelector('[data-testid="section-sources"]')).toBeNull();
  });
});

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

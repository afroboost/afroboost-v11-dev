// V595 — Vue d'ensemble / Résultats : calculs purs, aucune donnée inventée.
import {
  nicheDe, paysDe, villeDe, canalDe, etapes, compter, tauxDe, grouper, rdvParFicheDe, campagneDe,
} from '../prospectionStats';

const f = (sur) => ({ id: 'x', status: 'a_contacter', created_at: '2026-10-09T05:00:00+00:00', ...sur });

describe('déductions (champs absents en base)', () => {
  test('niche : la vague GV prime, sinon la catégorie', () => {
    expect(nicheDe(f({ wave: 'GV 10-2026 — E Entreprises', category: 'commerce' }))).toBe('E');
    expect(nicheDe(f({ wave: 'GV 10-2026 — D Écoles de danse France', category: 'ecole_danse' }))).toBe('D');
    expect(nicheDe(f({ wave: 'FESTIVALS 2027', category: 'association' }))).toBe('C');
    expect(nicheDe(f({ wave: 'Vague 1', category: 'bar' }))).toBe('A');
    expect(nicheDe(f({ wave: null, category: 'communaute_etudiante' }))).toBe('B');
    expect(nicheDe(f({ category: 'inconnue' }))).toBeNull();
  });
  test('pays : France seulement si écrit', () => {
    expect(paysDe(f({ city: 'Paris (France)' }))).toBe('France');
    expect(paysDe(f({ city: 'Neuchâtel' }))).toBe('Suisse');
    expect(paysDe(f({ city: 'Lyon', wave: 'GV 10-2026 — D Écoles de danse France' }))).toBe('France');
  });
  test('ville principale', () => {
    expect(villeDe(f({ city: 'Lyon (France) — Meyzieu / Bron' }))).toBe('Lyon');
    expect(villeDe(f({ city: 'Carouge (GE) & Nyon' }))).toBe('Carouge');
    expect(villeDe(f({ city: 'Genève / Nyon' }))).toBe('Genève');
    expect(villeDe(f({ city: 'La Chaux-de-Fonds' }))).toBe('La Chaux-de-Fonds');
  });
  test('canal : le premier cité', () => {
    expect(canalDe(f({ preferred_channel: 'E-mail' }))).toBe('email');
    expect(canalDe(f({ preferred_channel: 'Instagram DM' }))).toBe('instagram');
    expect(canalDe(f({ preferred_channel: 'Visite / DM' }))).toBe('visite');
    expect(canalDe(f({ preferred_channel: 'DM / e-mail' }))).toBe('instagram');
    expect(canalDe(f({ preferred_channel: 'Formulaire / contact paris.fr' }))).toBe('formulaire');
    expect(canalDe(f({ preferred_channel: 'Tél / visite' }))).toBe('telephone');
    expect(canalDe(f({ preferred_channel: 'WhatsApp' }))).toBe('autre');
    expect(canalDe(f({ preferred_channel: 'À trouver' }))).toBe('a_trouver');
    expect(canalDe(f({ preferred_channel: 'E-mail (à obtenir)' }))).toBe('a_trouver');
  });
});

describe('entonnoir', () => {
  const fiches = [
    f({ id: '1' }),
    f({ id: '2', status: 'contacte', first_contact_sent_at: '2026-09-03T08:00:00+00:00' }),
    f({ id: '3', status: 'repondu', first_contact_sent_at: '2026-09-03T08:00:00+00:00', replied_at: '2026-09-04T05:00:00+00:00' }),
    f({ id: '4', status: 'refuse', first_contact_sent_at: '2026-09-03T08:00:00+00:00' }),
    f({ id: '5', status: 'a_contacter', partner_id: 'p1' }),
  ];
  test('compteurs du « Tout »', () => {
    const c = compter(fiches);
    expect(c).toMatchObject({ total: 5, a_contacter: 1, contacte: 4, reponse: 2, interesse: 1, rdv: 0, accepte: 1, refuse: 1, sans_reponse: 2 });
  });
  test('rendez-vous : seulement les vrais, non annulés', () => {
    const rdv = rdvParFicheDe([
      { id: 'e1', event_type: 'appointment', prospect_id: '2', starts_at: '2026-10-10T10:00:00+00:00', status: 'prevu' },
      { id: 'e2', event_type: 'appointment', prospect_id: '3', starts_at: '2026-10-10T10:00:00+00:00', status: 'annule' },
      { id: 'e3', event_type: 'task', prospect_id: '4', starts_at: '2026-10-10T10:00:00+00:00' },
    ]);
    expect(Object.keys(rdv)).toEqual(['2']);
    expect(etapes(fiches[1], rdv).rdv).toBe(true);
    expect(compter(fiches, { rdvParFiche: rdv }).rdv).toBe(1);
  });
  test('période : une étape sans date ne compte que dans « Tout »', () => {
    const maintenant = Date.parse('2026-10-09T12:00:00Z');
    const c7 = compter(fiches, { periode: '7j', maintenant });
    expect(c7.total).toBe(5);       // créées le 09/10
    expect(c7.contacte).toBe(0);    // premiers envois du 03/09
    expect(c7.accepte).toBe(0);     // pas de date en base
    const c3m = compter(fiches, { periode: '3m', maintenant });
    expect(c3m.contacte).toBe(3);
    expect(c3m.reponse).toBe(1);
  });
  test('taux : « — » (null) sans dénominateur, jamais un faux 0 %', () => {
    expect(tauxDe(compter([]))).toEqual({ reponse: null, interet: null, rdv: null, conversion: null });
    expect(tauxDe(compter(fiches)).reponse).toBe(50);
  });
  test('grouper + campagne', () => {
    const g = grouper(fiches.map((x, i) => ({ ...x, city: i < 3 ? 'Neuchâtel' : 'Paris (France)' })), paysDe);
    expect(g.map((x) => [x.cle, x.n])).toEqual([['Suisse', 3], ['France', 2]]);
    expect(campagneDe(f({ wave: 'GV 10-2026 — D Écoles de danse France' }))).toBe('Grande vague — Écoles de danse France');
    expect(campagneDe(f({ wave: null }))).toBe('Premières fiches (sans vague)');
  });
});

/**
 * V646 — objectif / appel à l'action / à la une : le module pur.
 */
import { OBJECTIFS, CTAS, objectifLibelle, estALaUne, ctaDe } from '../publicationsConversion';

const ACTIONS = {
  onReserve: jest.fn(), onSessions: jest.fn(), onLive: jest.fn(), onBoutique: jest.fn(),
};

beforeEach(() => jest.clearAllMocks());

test('les vocabulaires sont fermés et sans doublon', () => {
  expect(OBJECTIFS.map((o) => o.id)).toEqual(
    ['temoignage', 'motivation', 'ambiance', 'concept', 'benefices', 'boutique', 'live']);
  expect(CTAS.map((c) => c.id)).toEqual(['essai', 'seances', 'live', 'boutique', 'offres']);
  expect(new Set(CTAS.map((c) => c.id)).size).toBe(CTAS.length);
  CTAS.forEach((c) => { expect(typeof c.libelle).toBe('string'); expect(c.libelle.length).toBeGreaterThan(3); });
});

test('objectifLibelle : traduit, ignore l’inconnu et l’absent', () => {
  expect(objectifLibelle({ objectif: 'temoignage' })).toBe('Témoignage / avis');
  expect(objectifLibelle({ objectif: 'TEMOIGNAGE' })).toBe('Témoignage / avis');
  expect(objectifLibelle({ objectif: 'inventé' })).toBe('');
  expect(objectifLibelle({})).toBe('');
  expect(objectifLibelle(null)).toBe('');
});

test('estALaUne : seul le drapeau du coach compte', () => {
  expect(estALaUne({ a_la_une: true })).toBe(true);
  expect(estALaUne({ a_la_une: false })).toBe(false);
  expect(estALaUne({})).toBe(false);
  expect(estALaUne(null)).toBe(false);
});

describe('ctaDe', () => {
  test('chaque CTA pointe vers le rappel attendu, et lui seul', () => {
    const attendu = { essai: 'onReserve', seances: 'onSessions', live: 'onLive', boutique: 'onBoutique', offres: 'onReserve' };
    Object.keys(attendu).forEach((id) => {
      const c = ctaDe({ cta: id }, ACTIONS);
      expect(c).toBeTruthy();
      c.lancer();
      expect(ACTIONS[attendu[id]]).toHaveBeenCalled();
      jest.clearAllMocks();
    });
  });
  test('aucun CTA posé -> null (pas de bouton sur la carte)', () => {
    expect(ctaDe({}, ACTIONS)).toBeNull();
    expect(ctaDe({ cta: '' }, ACTIONS)).toBeNull();
    expect(ctaDe(null, ACTIONS)).toBeNull();
  });
  test('CTA inconnu -> null : on n’invente pas une destination', () => {
    expect(ctaDe({ cta: 'teleportation' }, ACTIONS)).toBeNull();
  });
  test('rappel absent de la page -> null : jamais un bouton qui ne mène nulle part', () => {
    expect(ctaDe({ cta: 'live' }, { onReserve: jest.fn() })).toBeNull();
    expect(ctaDe({ cta: 'live' }, null)).toBeNull();
  });
  test('l’icône demandée est un nom, jamais un emoji', () => {
    CTAS.forEach((c) => expect(c.icone).toMatch(/^[a-zA-Z]+$/));
  });
});

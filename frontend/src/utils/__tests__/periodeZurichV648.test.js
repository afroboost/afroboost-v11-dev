/**
 * V648 — les bornes d'une période, en heure de Neuchâtel.
 * Les dates sont stockées en UTC : « aujourd'hui » ne commence PAS à minuit UTC.
 */
import { bornesPeriode, debutJourZurich, jourZurich, PERIODES_PROSPECTS } from '../periodeZurich';

const JOUR = 86400000;

test('la liste des périodes est celle demandée', () => {
  expect(PERIODES_PROSPECTS.map((p) => p.id)).toEqual(['tout', 'aujourdhui', '7j', '30j', 'perso']);
});

describe('debutJourZurich : minuit à Neuchâtel, exprimé en UTC', () => {
  test('heure d’hiver (UTC+1) : minuit local = 23:00 UTC la veille', () => {
    expect(new Date(debutJourZurich('2026-11-10')).toISOString()).toBe('2026-11-09T23:00:00.000Z');
  });
  test('heure d’été (UTC+2) : minuit local = 22:00 UTC la veille', () => {
    expect(new Date(debutJourZurich('2026-07-10')).toISOString()).toBe('2026-07-09T22:00:00.000Z');
  });
  test('une entrée qui n’est pas un jour ne lève pas', () => {
    expect(Number.isNaN(debutJourZurich('pas-un-jour'))).toBe(true);
    expect(Number.isNaN(debutJourZurich(''))).toBe(true);
    expect(Number.isNaN(debutJourZurich(null))).toBe(true);
  });
});

describe('jourZurich', () => {
  test('22:30 UTC un soir d’été, c’est DÉJÀ le lendemain à Neuchâtel', () => {
    expect(jourZurich(Date.parse('2026-07-09T22:30:00Z'))).toBe('2026-07-10');
  });
  test('23:30 UTC un soir d’hiver, c’est déjà le lendemain', () => {
    expect(jourZurich(Date.parse('2026-11-09T23:30:00Z'))).toBe('2026-11-10');
  });
});

describe('bornesPeriode', () => {
  const MIDI = Date.parse('2026-11-10T12:00:00Z');

  test('toutes les dates : aucune borne', () => {
    expect(bornesPeriode('tout', MIDI)).toEqual({ depuis_iso: '', jusqu_a_iso: '' });
  });

  test('aujourd’hui : de minuit local à minuit local du lendemain (borne exclue)', () => {
    expect(bornesPeriode('aujourdhui', MIDI)).toEqual({
      depuis_iso: '2026-11-09T23:00:00.000Z',
      jusqu_a_iso: '2026-11-10T23:00:00.000Z',
    });
  });

  test('aujourd’hui tient encore à 00h30 locale (soit 23h30 UTC la veille)', () => {
    const nuit = Date.parse('2026-11-09T23:30:00Z');   // 00:30 à Neuchâtel le 10
    expect(bornesPeriode('aujourdhui', nuit).depuis_iso).toBe('2026-11-09T23:00:00.000Z');
  });

  test('7 derniers jours : la fenêtre en couvre SEPT, aujourd’hui compris', () => {
    const b = bornesPeriode('7j', MIDI);
    const jours = (Date.parse(b.jusqu_a_iso) - Date.parse(b.depuis_iso)) / JOUR;
    expect(jours).toBe(7);
    expect(b.depuis_iso).toBe('2026-11-03T23:00:00.000Z');
  });

  test('30 derniers jours : trente jours, et le passage à l’heure d’hiver est absorbé', () => {
    const b = bornesPeriode('30j', MIDI);
    const heures = (Date.parse(b.jusqu_a_iso) - Date.parse(b.depuis_iso)) / 3600000;
    // 30 jours dont celui du changement d'heure (25 h) -> 721 h, pas 720.
    expect(heures).toBe(721);
    expect(b.depuis_iso).toBe('2026-10-11T22:00:00.000Z');   // encore l'heure d'été
  });

  test('période personnalisée : début inclus, FIN INCLUSE', () => {
    expect(bornesPeriode('perso', MIDI, '2026-11-01', '2026-11-10')).toEqual({
      depuis_iso: '2026-10-31T23:00:00.000Z',
      jusqu_a_iso: '2026-11-10T23:00:00.000Z',
    });
  });

  test('une seule borne fournie reste utilisable', () => {
    expect(bornesPeriode('perso', MIDI, '2026-11-01', '')).toEqual({
      depuis_iso: '2026-10-31T23:00:00.000Z', jusqu_a_iso: '',
    });
    expect(bornesPeriode('perso', MIDI, '', '2026-11-10')).toEqual({
      depuis_iso: '', jusqu_a_iso: '2026-11-10T23:00:00.000Z',
    });
  });

  test('une période inconnue ne filtre rien plutôt que de filtrer au hasard', () => {
    expect(bornesPeriode('la-semaine-prochaine', MIDI)).toEqual({ depuis_iso: '', jusqu_a_iso: '' });
  });
});

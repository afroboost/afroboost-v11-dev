/**
 * Appartenance et archivage sont deux questions differentes.
 * Les confondre rendait les vraies seances du coach non modifiables.
 */
import { appartientAuCoach } from '../courseOwnership';

const COACH = 'contact@exemple.com';
const ctx = { coachEmail: COACH, isSuperAdmin: false };

describe('appartientAuCoach', () => {
  test('un cours ARCHIVE du coach reste le sien — c\'est le cas reel', () => {
    const vrai = { id: 'merc', coach_id: COACH, archived: true, visible: true };
    expect(appartientAuCoach(vrai, ctx)).toBe(true);
  });

  test('l\'archivage n\'entre pas dans la decision, dans un sens comme dans l\'autre', () => {
    for (const archived of [true, false, undefined]) {
      expect(appartientAuCoach({ coach_id: COACH, archived }, ctx)).toBe(true);
    }
  });

  test('la visibilite non plus', () => {
    for (const visible of [true, false, undefined]) {
      expect(appartientAuCoach({ coach_id: COACH, visible }, ctx)).toBe(true);
    }
  });

  test('le cours d\'un autre coach n\'est jamais modifiable', () => {
    expect(appartientAuCoach({ coach_id: 'ailleurs@exemple.com' }, ctx)).toBe(false);
  });

  test('la comparaison ignore la casse', () => {
    expect(appartientAuCoach({ coach_id: 'CONTACT@Exemple.COM' }, ctx)).toBe(true);
  });

  test('le super-admin possede tout', () => {
    expect(appartientAuCoach({ coach_id: 'ailleurs@exemple.com' },
      { coachEmail: COACH, isSuperAdmin: true })).toBe(true);
  });

  test('sans identite connue, on n\'interdit pas — comportement historique', () => {
    expect(appartientAuCoach({ coach_id: 'x@y.z' }, { coachEmail: '' })).toBe(true);
  });

  test('un cours sans proprietaire n\'appartient a personne', () => {
    expect(appartientAuCoach({ id: 'orphelin' }, ctx)).toBe(false);
  });

  test('une entree aberrante ne fait rien tomber', () => {
    expect(appartientAuCoach(null, ctx)).toBe(false);
    expect(appartientAuCoach(undefined)).toBe(false);
  });
});

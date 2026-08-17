/**
 * Le seuil mobile, aux largeurs réelles demandées : 375, 390, 430, 768, desktop.
 */
import { SEUIL_MOBILE } from '../useLargeurEcran';

describe('CONTACTS V2 — largeurs réelles', () => {
  const cas = [
    [375, true, 'iPhone SE / mini'],
    [390, true, 'iPhone standard'],
    [430, true, 'iPhone Pro Max'],
    [560, true, 'petite tablette portrait'],
    [768, false, 'tablette'],
    [1024, false, 'desktop'],
    [1440, false, 'grand écran'],
  ];
  test.each(cas)('%i px → mobile=%s (%s)', (largeur, attendu) => {
    expect(largeur < SEUIL_MOBILE).toBe(attendu);
  });

  test('le seuil sépare bien la tablette du téléphone', () => {
    expect(SEUIL_MOBILE).toBeGreaterThan(430);
    expect(SEUIL_MOBILE).toBeLessThanOrEqual(768);
  });
});

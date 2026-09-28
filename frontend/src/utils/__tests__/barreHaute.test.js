/**
 * V554 — la barre haute : quatre cas, et un minuteur de largeur fixe.
 */
import { etatBarreHaute, minuteurBarre } from '../barreHaute';

describe('etatBarreHaute', () => {
  test('ni compte à rebours ni vue visiteur : aucune barre', () => {
    expect(etatBarreHaute({ compteActif: false, modeVisiteur: false })).toEqual({ visible: false, compte: false, retour: false, disposition: null });
    expect(etatBarreHaute(undefined).visible).toBe(false);
  });
  test('compte à rebours seul', () => {
    expect(etatBarreHaute({ compteActif: true, modeVisiteur: false }).disposition).toBe('compte');
  });
  test('vue visiteur seule : le retour a sa barre, sans compte à rebours', () => {
    const e = etatBarreHaute({ compteActif: false, modeVisiteur: true });
    expect(e.visible).toBe(true);
    expect(e.disposition).toBe('retour');
  });
  test('les deux : une seule barre, deux zones', () => {
    const e = etatBarreHaute({ compteActif: true, modeVisiteur: true });
    expect(e.disposition).toBe('retour-compte');
    expect(e.compte && e.retour).toBe(true);
  });
});

describe('minuteurBarre', () => {
  test('format stable « 00j 00h 00m 00s »', () => {
    expect(minuteurBarre(0)).toBe('00j 00h 00m 00s');
    expect(minuteurBarre(3 * 86400 + 4 * 3600 + 5 * 60 + 6)).toBe('03j 04h 05m 06s');
  });
  test('la largeur ne change jamais d\'une seconde à l\'autre', () => {
    expect(minuteurBarre(59).length).toBe(minuteurBarre(60).length);
    expect(minuteurBarre(86399).length).toBe(minuteurBarre(86400).length);
  });
  test('valeurs invalides ou négatives -> zéro', () => {
    expect(minuteurBarre(-5)).toBe('00j 00h 00m 00s');
    expect(minuteurBarre('x')).toBe('00j 00h 00m 00s');
  });
});

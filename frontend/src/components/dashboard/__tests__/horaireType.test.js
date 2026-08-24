/**
 * UNE OFFRE MELANGE DES RECURRENCES ET DES DATES UNIQUES.
 *
 * Le defaut ferme ici : le bouton « Date unique » posait `date: ''` alors que
 * l'ecran ne revele le champ date que si `date` est NON VIDE. Cliquer sur un
 * horaire recurrent ne changeait donc rien — le bouton etait mecaniquement
 * inerte, et aucun bloc ne pouvait devenir ponctuel.
 *
 * Le contrat de STOCKAGE ne bouge pas : `date` non vide = ponctuel, c'est ce
 * que lit `_v184_next_occurrences` cote serveur. Ce qu'on ajoute, c'est un
 * etat d'ECRAN — « ce bloc est en date unique, la date n'est pas encore
 * saisie » — que le stockage n'avait aucune raison de porter.
 */
import {
  estPonctuel, basculerHebdo, payloadDateWeekday,
  ponctuelsSansDate, weekdayDepuisDate,
} from '../horaireType';

const HEBDO_LUNDI = { id: 'a', weekday: 1, date: '', time: '18:30' };
const HEBDO_MERCREDI = { id: 'b', weekday: 3, date: '', time: '18:30' };
const UNIQUE_SAMEDI = { id: 'c', weekday: 6, date: '2026-08-29', time: '14:30' };

describe('le type se lit sur la date, et sur l\'intention du coach', () => {
  test('une date non vide fait un bloc ponctuel, sans rien d\'autre', () => {
    expect(estPonctuel(UNIQUE_SAMEDI, [])).toBe(true);
  });

  test('un bloc sans date est hebdomadaire', () => {
    expect(estPonctuel(HEBDO_LUNDI, [])).toBe(false);
  });

  test('LE BUG : « Date unique » clique sur un bloc recurrent doit le rendre ponctuel AVANT toute date', () => {
    expect(estPonctuel(HEBDO_LUNDI, ['a'])).toBe(true);
  });

  test('l\'intention d\'ecran ne contamine pas les autres blocs', () => {
    expect(estPonctuel(HEBDO_MERCREDI, ['a'])).toBe(false);
  });

  test('une date deja saisie rend le bloc ponctuel meme sans intention d\'ecran', () => {
    expect(estPonctuel(UNIQUE_SAMEDI, ['a'])).toBe(true);
  });
});

describe('revenir en hebdomadaire', () => {
  test('la date est effacee et le jour retenu est celui de cette date', () => {
    const r = basculerHebdo(UNIQUE_SAMEDI);
    expect(r.date).toBe('');
    expect(r.weekday).toBe(6);        // 2026-08-29 est un samedi
  });

  test('sans date exploitable, le jour existant est conserve — jamais force a dimanche', () => {
    expect(basculerHebdo({ id: 'x', weekday: 3, date: '' }).weekday).toBe(3);
    expect(basculerHebdo({ id: 'x', date: '' }).weekday).toBe(0);
  });
});

describe('ce qui part au serveur', () => {
  test('un bloc hebdomadaire part avec une date VIDE, jamais nulle', () => {
    expect(payloadDateWeekday(HEBDO_MERCREDI)).toEqual({ date: '', weekday: 3 });
  });

  test('un bloc ponctuel part avec sa date et le jour DERIVE de cette date', () => {
    expect(payloadDateWeekday(UNIQUE_SAMEDI)).toEqual({ date: '2026-08-29', weekday: 6 });
  });

  test('une date invalide ne fabrique pas un ponctuel fantome', () => {
    expect(payloadDateWeekday({ weekday: 2, date: 'n\'importe quoi' }))
      .toEqual({ date: '', weekday: 2 });
  });

  test('LE MELANGE : deux recurrences et une date unique gardent chacune son type', () => {
    const offre = [HEBDO_LUNDI, HEBDO_MERCREDI, UNIQUE_SAMEDI];
    expect(offre.map(payloadDateWeekday)).toEqual([
      { date: '', weekday: 1 },
      { date: '', weekday: 3 },
      { date: '2026-08-29', weekday: 6 },
    ]);
  });

  test('sauvegarder sans rien toucher ne convertit aucun bloc', () => {
    const offre = [HEBDO_LUNDI, HEBDO_MERCREDI, UNIQUE_SAMEDI];
    const apres = offre.map(c => ({ ...c, ...payloadDateWeekday(c) }));
    expect(apres.map(c => c.date)).toEqual(['', '', '2026-08-29']);
    expect(apres.map(c => c.weekday)).toEqual([1, 3, 6]);
    expect(apres.map(payloadDateWeekday)).toEqual(offre.map(payloadDateWeekday));
  });
});

describe('on ne devine pas une date a la place du coach', () => {
  test('un bloc mis en « date unique » sans date est signale, pas converti en douce', () => {
    expect(ponctuelsSansDate([HEBDO_LUNDI, HEBDO_MERCREDI], ['a'])).toEqual(['a']);
  });

  test('rien a signaler quand chaque bloc ponctuel porte sa date', () => {
    expect(ponctuelsSansDate([HEBDO_LUNDI, UNIQUE_SAMEDI], ['c'])).toEqual([]);
  });
});

describe('le jour de la semaine derive d\'une date', () => {
  test('convention JS — dimanche vaut 0', () => {
    expect(weekdayDepuisDate('2026-08-30')).toBe(0);
    expect(weekdayDepuisDate('2026-08-29')).toBe(6);
  });
  test('une entree inexploitable ne rend rien', () => {
    expect(weekdayDepuisDate('')).toBe(null);
    expect(weekdayDepuisDate('2026-13-45')).toBe(null);
  });
});

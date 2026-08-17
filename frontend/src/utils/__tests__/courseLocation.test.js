/**
 * L'alias `location` ne doit jamais rester sur l'adresse precedente.
 * C'est le defaut exact observe en production : `locationName` disait
 * « Jeunes-Rives » pendant que `location` disait encore « Auvernier ».
 */
import { alignerLieu } from '../courseLocation';

describe('alignerLieu', () => {
  test('l\'alias suit la valeur metier quand elle change', () => {
    const avant = { id: 'c1', locationName: 'Lausanne', location: 'Auvernier' };
    expect(alignerLieu(avant).location).toBe('Lausanne');
  });

  test('le scenario reel : Auvernier -> Jeunes-Rives ne laisse rien derriere', () => {
    const lu = { id: 'merc', locationName: 'Bord du Lac, Auvernier', location: 'Bord du Lac, Auvernier' };
    const edite = { ...lu, locationName: 'Jeunes-Rives, Neuchâtel' };
    const envoye = alignerLieu(edite);
    expect(envoye.locationName).toBe('Jeunes-Rives, Neuchâtel');
    expect(envoye.location).toBe('Jeunes-Rives, Neuchâtel');
    expect(envoye.location).not.toBe('Bord du Lac, Auvernier');
  });

  test('et dans l\'autre sens, autant de fois qu\'on veut', () => {
    let c = { id: 'x', locationName: 'A', location: 'A' };
    for (const lieu of ['B', 'C', 'A', 'D']) {
      c = alignerLieu({ ...c, locationName: lieu });
      expect(c.location).toBe(lieu);
    }
  });

  test('un lieu vide ne detruit pas l\'alias existant', () => {
    expect(alignerLieu({ locationName: '', location: 'Auvernier' }).location).toBe('Auvernier');
    expect(alignerLieu({ locationName: '   ', location: 'Auvernier' }).location).toBe('Auvernier');
  });

  test('un cours sans lieu du tout traverse sans dommage', () => {
    expect(alignerLieu({ id: 'y' })).toEqual({ id: 'y' });
  });

  test('aucun autre champ n\'est touche — ni jour, ni heure, ni publication', () => {
    const c = { id: 'z', name: 'Cours', weekday: 3, time: '18:30', mapsUrl: 'https://m',
                visible: true, archived: true, locationName: 'Lausanne', location: 'Auvernier' };
    const r = alignerLieu(c);
    expect(r.weekday).toBe(3);
    expect(r.time).toBe('18:30');
    expect(r.mapsUrl).toBe('https://m');
    expect(r.visible).toBe(true);
    expect(r.archived).toBe(true);
    expect(r.name).toBe('Cours');
  });

  test('l\'objet d\'origine n\'est pas mute', () => {
    const c = { locationName: 'Lausanne', location: 'Auvernier' };
    alignerLieu(c);
    expect(c.location).toBe('Auvernier');
  });

  test('une entree aberrante ne fait pas tomber l\'enregistrement', () => {
    expect(alignerLieu(null)).toBeNull();
    expect(alignerLieu(undefined)).toBeUndefined();
  });
});

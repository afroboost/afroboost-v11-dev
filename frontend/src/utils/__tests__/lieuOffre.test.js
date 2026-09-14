/**
 * Le lieu d'une offre a UNE source, et c'est celle que le coach modifie.
 *
 * Le bug fermé ici, mesuré en production le 14/09/2026 : « Mes offres »
 * affichait « Bord du Lac, Auvernier » et l'accueil « Chem. des Valangines 97 ».
 * L'admin écrivait `offer.location`, la carte visiteur lisait le lieu du PREMIER
 * cours lié — et masquait `offer.location` dès qu'un cours lié en avait un.
 * Modifier le lieu n'avait donc aucun effet visible, et le cours « premier »
 * n'était même pas choisi : c'était l'ordre de `linked_course_ids`.
 */
import { lieuOffre, lienMapsLieu } from '../lieuOffre';

const COURS_PERIME = { id: 'c1', locationName: 'Chem. des Valangines 97, 2000 Neuchâtel' };
const COURS_A_JOUR = { id: 'c2', locationName: 'Bord du Lac, Auvernier, Neuchâtel' };

describe('lieuOffre', () => {
  test('LE BUG : le lieu de l’offre gagne sur celui du premier cours lié', () => {
    const offre = {
      location: 'Bord du Lac, Auvernier, Neuchâtel',
      linkedCourses: [COURS_PERIME, COURS_A_JOUR],
    };
    expect(lieuOffre(offre)).toEqual({
      texte: 'Bord du Lac, Auvernier, Neuchâtel', source: 'offre', cours: null,
    });
  });

  test('sans lieu sur l’offre, le cours lié sert de repli — rien ne change pour ces offres', () => {
    const r = lieuOffre({ location: '', linkedCourses: [COURS_PERIME] });
    expect(r.texte).toBe('Chem. des Valangines 97, 2000 Neuchâtel');
    expect(r.source).toBe('cours');
  });

  test('un lieu fait d’espaces n’est pas un lieu', () => {
    const r = lieuOffre({ location: '   ', linkedCourses: [COURS_A_JOUR] });
    expect(r.source).toBe('cours');
    expect(lieuOffre({ location: '   ', linkedCourses: [{ id: 'x', locationName: '  ' }] }))
      .toEqual({ texte: '', source: 'aucun', cours: null });
  });

  test('`location_address` (champ structuré R3a) sert quand `location` est vide', () => {
    expect(lieuOffre({ location: '', location_address: 'Quai Ostervald, Neuchâtel' }).texte)
      .toBe('Quai Ostervald, Neuchâtel');
  });

  test('aucun lieu nulle part : rien à afficher, et pas de « undefined »', () => {
    expect(lieuOffre({}).texte).toBe('');
    expect(lieuOffre(null).texte).toBe('');
    expect(lieuOffre({ linkedCourses: null }).texte).toBe('');
  });
});

describe('lienMapsLieu', () => {
  test('le lien pointe sur le lieu AFFICHÉ, pas sur un autre', () => {
    const offre = { location: 'Bord du Lac, Auvernier, Neuchâtel', linkedCourses: [COURS_PERIME] };
    expect(lienMapsLieu(offre)).toContain(encodeURIComponent('Bord du Lac, Auvernier, Neuchâtel'));
    expect(lienMapsLieu(offre)).not.toContain('Valangines');
  });

  test('le `mapsUrl` du cours n’est retenu que si le cours est la source retenue', () => {
    const cours = { id: 'c', locationName: 'Plage Est', mapsUrl: 'https://maps.example/plage' };
    expect(lienMapsLieu({ location: '', linkedCourses: [cours] })).toBe('https://maps.example/plage');
    // Lieu propre à l'offre : on ne pointe pas vers la carte d'un autre endroit.
    expect(lienMapsLieu({ location: 'Auvernier', linkedCourses: [cours] }))
      .toBe('https://www.google.com/maps/search/?api=1&query=Auvernier');
  });

  test('garde XSS : une URL `javascript:` ne devient jamais un href', () => {
    const cours = { id: 'c', locationName: 'Plage', mapsUrl: 'javascript:alert(1)' };
    expect(lienMapsLieu({ location: '', linkedCourses: [cours] })).toMatch(/^https:\/\/www\.google\.com/);
  });

  test('pas de lieu, pas de lien', () => {
    expect(lienMapsLieu({})).toBeNull();
  });
});

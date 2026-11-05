// V647 — une carte par cours physique : le regroupement n'obéit qu'au serveur, aucun rattachement n'est perdu.
jest.mock('axios', () => ({ __esModule: true, default: { get: jest.fn() } }));
const fs = require('fs');
const path = require('path');
const { normaliserAgenda, regrouperSeancesPhysiques } = require('../SessionsModal');
const { fusionnerDetailsSession } = require('../coach/InscritsSession');

const G = 'forfait+publiee';
const Q = '2026-11-11T18:45:00';
const AGENDA = [
  { course_id: 'publiee', name: "Cours à l'unité", locationName: 'Chemin des Valangines 97', datetime: Q, recurrent: true,
    seance_physique: G, seance_principale: false,
    offers: [{ id: 'unite', name: 'Unité' }, { id: 'essai', name: 'Essai' }, { id: 'flex', name: 'Flex' }] },
  { course_id: 'forfait', name: 'Afroboost Silent – Session Cardio', locationName: 'Chem. des Valangines 97)', datetime: Q, recurrent: true,
    seance_physique: G, seance_principale: true,
    offers: [{ id: 'unite', name: 'Unité' }, { id: 'pulse', name: 'Pulse' }, { id: 'flex', name: 'Flex' }] },
  { course_id: 'evenement', name: 'Édition spéciale', locationName: 'Chemin des Valangines 97', datetime: Q, recurrent: false, offers: [{ id: 'evt', name: 'Billet' }] },
];

describe('regrouperSeancesPhysiques', () => {
  const liste = regrouperSeancesPhysiques(normaliserAgenda(AGENDA));
  const carte = liste.find((o) => o.seance === G);

  test('une seule carte pour les deux fiches', () => {
    expect(liste.filter((o) => o.seance === G)).toHaveLength(1);
  });
  test('un événement à la même heure et à la même adresse reste une carte à part', () => {
    expect(liste.map((o) => o.id)).toContain('evenement');
    expect(liste).toHaveLength(2);
  });
  test('le nom de la fiche forfait, l’adresse propre de la fiche publiée', () => {
    expect(carte.nom).toBe('Afroboost Silent – Session Cardio');
    expect(carte.lieu).toBe('Chemin des Valangines 97');
    expect(carte.id).toBe('forfait');
  });
  test('toutes les offres restent, sans doublon, la première offre ne change pas', () => {
    expect(carte.offres.map((o) => o.id)).toEqual(['unite', 'pulse', 'flex', 'essai']);
  });
  test('les deux fiches restent connues pour le détail coach', () => {
    expect(carte.ids).toEqual(['forfait', 'publiee']);
  });
  test('deux instants différents : deux cartes', () => {
    const autre = [AGENDA[0], { ...AGENDA[1], datetime: '2026-11-18T18:45:00' }];
    expect(regrouperSeancesPhysiques(normaliserAgenda(autre))).toHaveLength(2);
  });
  test('sans signal du serveur, même heure et même adresse : rien n’est regroupé', () => {
    const brut = AGENDA.map(({ seance_physique: _a, seance_principale: _b, ...o }) => o);
    expect(regrouperSeancesPhysiques(normaliserAgenda(brut))).toHaveLength(3);
  });
  test('une seule fiche ce jour-là (l’autre annulée) : la carte reste juste', () => {
    const seule = regrouperSeancesPhysiques(normaliserAgenda([AGENDA[0]]));
    expect(seule).toHaveLength(1);
    expect(seule[0].id).toBe('publiee');
    expect(seule[0].ids).toEqual(['publiee']);
  });
});

describe('fusionnerDetailsSession', () => {
  const p = (id, email, places = 1) => ({ id, nom: id, email, places });
  test('une seule fiche : renvoyée telle quelle', () => {
    const d = { inscrits: 1, participants: [p('a', 'a@x')] };
    expect(fusionnerDetailsSession([d])).toBe(d);
  });
  test('additionne les personnes différentes', () => {
    const f = fusionnerDetailsSession([
      { inscrits: 3, capacite: 30, participants: [p('a', 'a@x'), p('b', 'b@x', 2)], annulations: [{ nom: 'c' }] },
      { inscrits: 1, capacite: 30, participants: [p('d', 'd@x')], annulations: [{ nom: 'e' }] },
    ]);
    expect(f.inscrits).toBe(4);
    expect(f.participants.map((x) => x.id)).toEqual(['a', 'b', 'd']);
    expect(f.restantes).toBe(26);
    expect(f.annulations).toHaveLength(2);
  });
  test('la même personne sur les deux fiches : une ligne, un compte', () => {
    const f = fusionnerDetailsSession([
      { inscrits: 3, capacite: 30, participants: [p('a', 'a@x'), p('b', 'b@x', 2)] },
      { inscrits: 2, capacite: 30, participants: [p('a2', 'A@X'), p('c', 'c@x')] },
    ]);
    expect(f.inscrits).toBe(4);
    expect(f.participants.map((x) => x.id)).toEqual(['a', 'b', 'c']);
  });
  test('la même personne, plus de places sur la seconde fiche : le plus grand total', () => {
    const f = fusionnerDetailsSession([
      { inscrits: 1, participants: [p('a', 'a@x')] },
      { inscrits: 3, participants: [p('a2', 'a@x', 3)] },
    ]);
    expect(f.inscrits).toBe(3);
    expect(f.participants).toHaveLength(1);
    expect(f.participants[0].places).toBe(3);
  });
  test('deux réservations de la même personne sur UNE fiche : les deux restent', () => {
    const f = fusionnerDetailsSession([
      { inscrits: 2, participants: [p('a', 'a@x'), p('b', 'a@x')] },
      { inscrits: 0, participants: [] },
    ]);
    expect(f.inscrits).toBe(2);
    expect(f.participants).toHaveLength(2);
  });
  test('capacités en désaccord : aucune capacité inventée', () => {
    const f = fusionnerDetailsSession([{ inscrits: 0, capacite: 30, participants: [] }, { inscrits: 0, capacite: 20, participants: [] }]);
    expect(f.capacite).toBeNull();
    expect(f.complet).toBe(false);
  });
});

describe('bouton d’essai', () => {
  const app = fs.readFileSync(path.join(__dirname, '..', '..', 'App.js'), 'utf8');
  test('le bouton React redondant a disparu', () => {
    expect(app).not.toContain("RÉSERVER UN COURS D'ESSAI");
  });
  test('les horaires et l’adresse restent', () => {
    expect(app).toContain('MER 18H45 · DIM 18H30');
    expect(app).toContain('Chemin des Valangines 97 · 2000 Neuchâtel');
  });
  test('le Hero garde son bouton', () => {
    const hero = fs.readFileSync(path.join(__dirname, '..', 'HeroTexte.js'), 'utf8');
    expect(hero).toContain("const HREF_ESSAI = '/?link=b83914b4-c5a'");
    expect(hero).toContain('href={HREF_ESSAI}');
  });
});

import {
  normaliser, minutesDeLHeure, memeCreneau, creneauDejaPris,
  nomDeSeance, NOM_PROVISOIRE,
} from '../creneauDoublon';

const VAL = 'Chemin des Valangines 97, 2000 Neuchâtel';

describe('V663 — cours, séance et offre sont trois choses distinctes', () => {
  test('un nom d’OFFRE ne devient jamais le nom d’une séance', () => {
    const offres = ["Cours à l'unité", 'PULSE x10 cours', 'Membres', 'Saison hiver — 8 mois'];
    // Le cas exact mesuré en production.
    expect(nomDeSeance("Cours à l'unité", offres)).toBe(NOM_PROVISOIRE);
    // La comparaison est tolérante : accents, casse, apostrophe typographique.
    expect(nomDeSeance("COURS À L’UNITÉ", offres)).toBe(NOM_PROVISOIRE);
    expect(nomDeSeance('  membres  ', offres)).toBe(NOM_PROVISOIRE);
    // Un vrai nom d'activité passe, lui.
    expect(nomDeSeance('Afroboost Silent', offres)).toBe('Afroboost Silent');
    expect(nomDeSeance('Afroboost Live', offres)).toBe('Afroboost Live');
    // Vide -> libellé provisoire, jamais un nom commercial.
    expect(nomDeSeance('', offres)).toBe(NOM_PROVISOIRE);
    expect(nomDeSeance(null, offres)).toBe(NOM_PROVISOIRE);
  });

  test('AUCUNE exception codée pour un nom particulier', () => {
    // La règle vaut pour une offre FUTURE, inconnue aujourd'hui.
    expect(nomDeSeance('Formule Été 2027', ['Formule Été 2027'])).toBe(NOM_PROVISOIRE);
    // Et « Cours à l'unité » redevient un nom valable s'il n'est plus une offre.
    expect(nomDeSeance("Cours à l'unité", ['Membres'])).toBe("Cours à l'unité");
  });

  test('deux cours DIFFÉRENTS à la même heure restent deux créneaux', () => {
    // L'exemple 2 du cahier des charges : même mercredi, même heure, MAIS deux
    // activités réelles. Elles doivent rester distinctes si le lieu diffère.
    const a = { id: 'a', name: 'Afroboost Silent', weekday: 3, time: '18:45', locationName: VAL };
    const b = { id: 'b', name: 'Afroboost Live', weekday: 3, time: '18:45', locationName: 'ArtDanse, Martigny' };
    expect(memeCreneau(a, b)).toBe(false);
    expect(creneauDejaPris([a], b)).toBeNull();
  });

  test('le même créneau physique est reconnu (jour + heure + LIEU)', () => {
    const existant = { id: 'a', name: 'Afroboost Silent – Session Cardio', weekday: 3, time: '18:45', locationName: VAL };
    const nouveau = { weekday: 3, time: '18:45', locationName: 'chemin des valangines 97 2000 neuchatel' };
    expect(memeCreneau(existant, nouveau)).toBe(true);
    expect(creneauDejaPris([existant], nouveau).id).toBe('a');
  });

  test('ON NE DÉDUPLIQUE JAMAIS SUR LA SEULE DATE ET HEURE', () => {
    const a = { id: 'a', weekday: 3, time: '18:45', locationName: VAL };
    // Même jour, même heure, lieu INCONNU -> on ne conclut PAS.
    expect(memeCreneau(a, { weekday: 3, time: '18:45' })).toBe(false);
    expect(memeCreneau(a, { weekday: 3, time: '18:45', locationName: '' })).toBe(false);
    expect(creneauDejaPris([a], { weekday: 3, time: '18:45' })).toBeNull();
  });

  test('un cours ponctuel et un récurrent ne sont jamais rapprochés', () => {
    const recurrent = { id: 'r', weekday: 3, time: '18:45', locationName: VAL };
    const ponctuel = { date: '2026-11-25', time: '18:45', locationName: VAL };
    expect(memeCreneau(recurrent, ponctuel)).toBe(false);
    // Deux ponctuels ne se rapprochent que sur la MÊME date.
    expect(memeCreneau({ date: '2026-11-25', time: '18:45', locationName: VAL }, ponctuel)).toBe(true);
    expect(memeCreneau({ date: '2026-11-18', time: '18:45', locationName: VAL }, ponctuel)).toBe(false);
  });

  test('un cours ARCHIVÉ n’est jamais proposé au rattachement', () => {
    const archive = { id: 'old', weekday: 3, time: '18:45', locationName: VAL, archived: true };
    expect(creneauDejaPris([archive], { weekday: 3, time: '18:45', locationName: VAL })).toBeNull();
  });

  test('un cours ne se signale pas lui-même', () => {
    const c = { id: 'moi', weekday: 3, time: '18:45', locationName: VAL };
    expect(creneauDejaPris([c], c, 'moi')).toBeNull();
    expect(creneauDejaPris([c], c).id).toBe('moi');   // sans exclusion, il matche
  });

  test('l’heure est comparée en minutes, pas en texte', () => {
    expect(minutesDeLHeure('18:45')).toBe(1125);
    expect(minutesDeLHeure('18h45')).toBe(1125);
    expect(minutesDeLHeure('8:05')).toBe(485);
    expect(minutesDeLHeure('')).toBeNull();
    expect(minutesDeLHeure('25:00')).toBeNull();
    expect(minutesDeLHeure('18:70')).toBeNull();
    const a = { weekday: 0, time: '18:30', locationName: VAL };
    expect(memeCreneau(a, { weekday: 0, time: '18h30', locationName: VAL })).toBe(true);
    // Une heure illisible ne rapproche rien.
    expect(memeCreneau(a, { weekday: 0, time: 'bientôt', locationName: VAL })).toBe(false);
  });

  test('normaliser ignore accents, casse et ponctuation', () => {
    expect(normaliser('Chemin des Valangines 97, 2000 Neuchâtel'))
      .toBe(normaliser('chemin des valangines 97 2000 neuchatel'));
    expect(normaliser(null)).toBe('');
  });

  test('une liste vide ou cassée ne fait jamais planter', () => {
    expect(creneauDejaPris(null, { weekday: 3, time: '18:45', locationName: VAL })).toBeNull();
    expect(creneauDejaPris([null, undefined, {}], { weekday: 3, time: '18:45', locationName: VAL })).toBeNull();
    expect(creneauDejaPris([{ id: 'a' }], null)).toBeNull();
    expect(nomDeSeance('Afroboost Silent', null)).toBe('Afroboost Silent');
  });
});

import { TYPES, typeDe, actionDe, texteComplet, titreDe, aMontrer } from '../notificationGrande';

describe('V659 — reconnaître le sujet', () => {
  test('le type déclaré fait foi', () => {
    expect(typeDe({ type: 'reservation' })).toBe(TYPES.reservation);
    expect(typeDe({ type: 'COURS' })).toBe(TYPES.cours);
  });
  test('à défaut, le texte le dit', () => {
    expect(typeDe({ titre: 'Ta réservation est confirmée' })).toBe(TYPES.reservation);
    expect(typeDe({ texte: 'Il te reste 3 séances sur ton abonnement' })).toBe(TYPES.abonnement);
    expect(typeDe({ titre: 'Cours annulé ce soir' })).toBe(TYPES.cours);
    expect(typeDe({ titre: 'Paiement reçu' })).toBe(TYPES.paiement);
  });
  test('sans indice, on ne devine pas : « info »', () => {
    expect(typeDe({ titre: 'Bonjour' })).toBe(TYPES.info);
    expect(typeDe(null)).toBe(TYPES.info);
  });
});

describe('V659 — le texte n’est JAMAIS coupé', () => {
  test('un long message revient entier', () => {
    const long = 'A'.repeat(500);
    expect(texteComplet({ texte: long })).toHaveLength(500);
    expect(texteComplet({ texte: long })).not.toContain('…');
  });
  test('les différents noms de champ sont lus', () => {
    expect(texteComplet({ body: 'coucou' })).toBe('coucou');
    expect(texteComplet({ content: 'coucou' })).toBe('coucou');
    expect(texteComplet({})).toBe('');
  });
  test('le titre a un repli honnête', () => {
    expect(titreDe({ senderName: 'Coach Bassi' })).toBe('Coach Bassi');
    expect(titreDe({})).toBe('Afroboost');
    expect(titreDe({ titre: '   ' })).toBe('Afroboost');
  });
});

describe('V659 — une action seulement si elle mène quelque part', () => {
  test('pas de destination = pas de bouton', () => {
    expect(actionDe({ titre: 'Info' })).toBeNull();
    expect(actionDe(null)).toBeNull();
  });
  test('le libellé suit le sujet', () => {
    expect(actionDe({ type: 'reservation', url: '/espace' }).libelle).toBe('Voir ma réservation');
    expect(actionDe({ type: 'cours', url: '/espace' }).libelle).toBe('Voir mon cours');
    expect(actionDe({ type: 'abonnement', url: '/espace' }).libelle).toBe('Consulter mon abonnement');
  });
  test('une action fournie explicitement est respectée', () => {
    const a = { libelle: 'Ouvrir le Live', href: '/live' };
    expect(actionDe({ action: a })).toEqual(a);
    // Incomplète = ignorée : pas de bouton sans libellé ni destination.
    expect(actionDe({ action: { libelle: 'Vide' } })).toBeNull();
  });
});

describe('V659 — une seule fenêtre à la fois', () => {
  test('la plus récente NON LUE est choisie', () => {
    const f = [{ id: 1, lu: true }, { id: 2 }, { id: 3 }];
    expect(aMontrer(f).id).toBe(3);
  });
  test('si tout est lu, la plus récente', () => {
    expect(aMontrer([{ id: 1, lu: true }, { id: 2, read: true }]).id).toBe(2);
  });
  test('file vide ou absente : rien', () => {
    expect(aMontrer([])).toBeNull();
    expect(aMontrer(null)).toBeNull();
    expect(aMontrer([null, undefined])).toBeNull();
  });
});

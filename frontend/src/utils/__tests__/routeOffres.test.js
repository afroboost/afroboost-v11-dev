import { ouvrirLesOffres, parParametre, parChemin } from '../routeOffres';

describe('V655 — ouvrir les formules', () => {
  // LA PORTE D'ORIGINE RESTE OUVERTE. `?offres=toutes` est écrit dans la page
  // d'essai servie par le serveur et dans des liens déjà partagés : le casser
  // serait une régression que personne ne verrait tout de suite.
  test('`/?offres=toutes` ouvre encore, exactement comme avant', () => {
    expect(parParametre('?offres=toutes')).toBe(true);
    expect(ouvrirLesOffres('/', '?offres=toutes')).toBe(true);
    // Le paramètre marche depuis n'importe quel chemin, comme auparavant.
    expect(ouvrirLesOffres('/a-propos', '?offres=toutes')).toBe(true);
  });

  test('le nouveau chemin `/offres` ouvre la même porte', () => {
    expect(parChemin('/offres')).toBe(true);
    expect(ouvrirLesOffres('/offres', '')).toBe(true);
    expect(ouvrirLesOffres('/offres/', '')).toBe(true);   // barre finale
    expect(ouvrirLesOffres('/Offres', '')).toBe(true);    // casse
  });

  test("ce qui n'est PAS la page des offres ne l'ouvre pas", () => {
    // Un chemin qui commence par /offres sans en être : il irait ailleurs.
    expect(ouvrirLesOffres('/offres-speciales', '')).toBe(false);
    expect(ouvrirLesOffres('/offres/detail', '')).toBe(false);
    expect(ouvrirLesOffres('/', '')).toBe(false);
    expect(ouvrirLesOffres('/boutique', '')).toBe(false);
    expect(ouvrirLesOffres('/espace/AFR-2287CA', '')).toBe(false);
    // Une autre valeur du paramètre n'ouvre rien (V622 : seul `toutes`).
    expect(ouvrirLesOffres('/', '?offres=1')).toBe(false);
    expect(ouvrirLesOffres('/', '?offre=abc')).toBe(false);
  });

  test("une entrée illisible n'empêche jamais l'accueil de s'afficher", () => {
    expect(ouvrirLesOffres(null, null)).toBe(false);
    expect(ouvrirLesOffres(undefined, undefined)).toBe(false);
    expect(ouvrirLesOffres('', '')).toBe(false);
    expect(parParametre('%%%')).toBe(false);
  });

  test('les deux entrées mènent au MÊME signal (aucune seconde logique)', () => {
    // La fonction ne renvoie qu'un booléen : il n'existe pas deux chemins de
    // code différents selon l'entrée, donc pas de comportement divergent.
    expect(ouvrirLesOffres('/offres', '')).toBe(ouvrirLesOffres('/', '?offres=toutes'));
  });
});

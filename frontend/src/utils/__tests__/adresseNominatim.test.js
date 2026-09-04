/**
 * U1b — LE CONTRAT DU MODULE D'ADRESSES.
 *
 * Ce qu'on eprouve ici n'est pas « ca marche quand tout va bien » : c'est que
 * RIEN de ce que peut faire un service tiers gratuit ne remonte en exception.
 * Panne reseau, 500, JSON illisible, timeout, abandon, reponse d'une forme
 * inattendue : la reponse doit toujours etre une liste, jamais un rejet — sans
 * quoi une promesse non capturee ferait tomber l'ecran du coach.
 */
import {
  construireUrl,
  formaterAdresse,
  formaterDetail,
  normaliserReponse,
  chercherAdresses,
  nettoyerTexte,
  LONGUEUR_MIN
} from '../adresseNominatim';

const RESULTAT_CH = {
  place_id: 1,
  display_name: 'Rue des Vallangines, 97, Neuchâtel, District de Neuchâtel, Neuchâtel, 2000, Suisse',
  name: 'Rue des Vallangines',
  address: {
    road: 'Rue des Vallangines',
    house_number: '97',
    city: 'Neuchâtel',
    postcode: '2000',
    state: 'Neuchâtel',
    country: 'Suisse',
    country_code: 'ch'
  }
};

const RESULTAT_FR = {
  place_id: 2,
  display_name: 'Gare de Lyon, Paris, France',
  name: 'Gare de Lyon',
  address: { city: 'Paris', postcode: '75012', country: 'France', country_code: 'fr' }
};

function reponse(json, ok = true) {
  return Promise.resolve({ ok, json: () => Promise.resolve(json) });
}

describe("l'URL interrogee", () => {
  test('borne la recherche a la Suisse et a ses voisins', () => {
    const url = construireUrl('vallangines');
    expect(url).toContain('nominatim.openstreetmap.org/search');
    expect(url).toMatch(/countrycodes=ch(%2C|,)/);
    expect(url).toContain('format=jsonv2');
    expect(url).toContain('addressdetails=1');
    expect(url).toContain('limit=5');
  });

  test('le texte saisi est encode, jamais concatene brut', () => {
    const url = construireUrl('rue de l\'Hôpital & co');
    expect(url).not.toContain(' ');
    expect(url).toContain('q=');
  });
});

describe('le libelle propose', () => {
  test('est court et lisible, la ou display_name fait 80 caracteres', () => {
    expect(formaterAdresse(RESULTAT_CH)).toBe('Rue des Vallangines 97, 2000 Neuchâtel');
    expect(RESULTAT_CH.display_name.length).toBeGreaterThan(60);
  });

  test('garde le pays quand ce n\'est PAS la Suisse', () => {
    expect(formaterAdresse(RESULTAT_FR)).toBe('Gare de Lyon, 75012 Paris, France');
  });

  test('retombe sur display_name quand l\'adresse detaillee manque', () => {
    expect(formaterAdresse({ display_name: '  Plage Est  de St-Blaise ' }))
      .toBe('Plage Est de St-Blaise');
  });

  test('ne casse pas sur une entree absurde', () => {
    expect(formaterAdresse(null)).toBe('');
    expect(formaterAdresse(42)).toBe('');
    expect(formaterDetail(null)).toBe('');
  });
});

describe('la normalisation de la reponse', () => {
  test('deduplique et ignore les entrees vides', () => {
    const liste = normaliserReponse([RESULTAT_CH, RESULTAT_CH, {}, null, RESULTAT_FR]);
    expect(liste.map(x => x.libelle)).toEqual([
      'Rue des Vallangines 97, 2000 Neuchâtel',
      'Gare de Lyon, 75012 Paris, France'
    ]);
  });

  test('une reponse qui n\'est pas un tableau donne une liste vide', () => {
    expect(normaliserReponse({ erreur: 'rate limited' })).toEqual([]);
    expect(normaliserReponse(null)).toEqual([]);
    expect(normaliserReponse('<html>503</html>')).toEqual([]);
  });
});

describe('la recherche elle-meme', () => {
  test('propose les adresses quand le service repond', async () => {
    const faux = jest.fn(() => reponse([RESULTAT_CH]));
    const liste = await chercherAdresses('vallangines', { fetchImpl: faux });
    expect(faux).toHaveBeenCalledTimes(1);
    expect(liste[0].libelle).toBe('Rue des Vallangines 97, 2000 Neuchâtel');
  });

  test('n\'interroge RIEN sous la longueur minimale', async () => {
    const faux = jest.fn(() => reponse([RESULTAT_CH]));
    expect(LONGUEUR_MIN).toBeGreaterThanOrEqual(3);
    expect(await chercherAdresses('ne', { fetchImpl: faux })).toEqual([]);
    expect(await chercherAdresses('   ', { fetchImpl: faux })).toEqual([]);
    expect(faux).not.toHaveBeenCalled();
  });

  test('SERVICE EN PANNE : liste vide, aucune exception', async () => {
    const faux = jest.fn(() => Promise.reject(new Error('Failed to fetch')));
    await expect(chercherAdresses('neuchatel', { fetchImpl: faux })).resolves.toEqual([]);
  });

  test('SERVICE EN 503 : liste vide, aucune exception', async () => {
    const faux = jest.fn(() => reponse([], false));
    await expect(chercherAdresses('neuchatel', { fetchImpl: faux })).resolves.toEqual([]);
  });

  test('JSON ILLISIBLE : liste vide, aucune exception', async () => {
    const faux = jest.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.reject(new SyntaxError('Unexpected token <'))
    }));
    await expect(chercherAdresses('neuchatel', { fetchImpl: faux })).resolves.toEqual([]);
  });

  test('ABANDON (AbortError) : liste vide, aucune exception', async () => {
    const faux = jest.fn(() => {
      const e = new Error('The user aborted a request.');
      e.name = 'AbortError';
      return Promise.reject(e);
    });
    await expect(chercherAdresses('neuchatel', { fetchImpl: faux })).resolves.toEqual([]);
  });

  test('TIMEOUT : la requete est avortee et la liste revient vide', async () => {
    jest.useFakeTimers();
    const controleur = new AbortController();
    const faux = jest.fn((url, init) => new Promise((_, rejeter) => {
      init.signal.addEventListener('abort', () => {
        const e = new Error('aborted');
        e.name = 'AbortError';
        rejeter(e);
      });
    }));
    const promesse = chercherAdresses('neuchatel', { fetchImpl: faux, controleur, timeout: 100 });
    jest.advanceTimersByTime(200);
    await expect(promesse).resolves.toEqual([]);
    expect(controleur.signal.aborted).toBe(true);
    jest.useRealTimers();
  });

  test('sans fetch disponible (vieux navigateur) : liste vide, aucun crash', async () => {
    const sauvegarde = global.fetch;
    delete global.fetch;
    try {
      await expect(chercherAdresses('neuchatel')).resolves.toEqual([]);
    } finally {
      if (sauvegarde) global.fetch = sauvegarde;
    }
  });
});

describe('le nettoyage de texte', () => {
  test('ecrase les espaces multiples et rogne les bords', () => {
    // Les adresses reellement en base : « Vidy,  Lausanne », «  Plage Est... »
    expect(nettoyerTexte('Vidy,  Lausanne ')).toBe('Vidy, Lausanne');
    expect(nettoyerTexte(' Plage Est de St-Blaise - La Torpille'))
      .toBe('Plage Est de St-Blaise - La Torpille');
    expect(nettoyerTexte(null)).toBe('');
  });
});

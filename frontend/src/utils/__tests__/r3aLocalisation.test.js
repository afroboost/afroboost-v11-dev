// R3a — LA LOCALISATION, VUE DU NAVIGATEUR.
//
// CE QUI EST PROUVE ICI, ET POURQUOI CHAQUE POINT COMPTE :
//
//   * U1b N'A PAS REGRESSE : `cle`, `libelle` et `detail` sortent exactement
//     comme avant, et le composant se comporte a l'identique quand personne
//     ne lui passe le nouveau rappel ;
//   * la ville sort du MEME repli que celui deja utilise a l'interieur de
//     `formaterAdresse` — Auvernier arrive en `village`, Lausanne en `city` :
//     n'en lire qu'un seul perdrait la moitie des communes suisses ;
//   * choisir une proposition remplit ville ET coordonnees d'un coup, sans
//     seconde requete : Nominatim les a deja envoyees ;
//   * taper librement ne fabrique AUCUNE coordonnee — absent veut dire
//     « on ne sait pas », jamais « 0,0 » ;
//   * le formulaire d'offre envoie les quatre champs, et les RELIT.
import fs from 'fs';
import path from 'path';
import { normaliserReponse, extraireVille, formaterAdresse }
  from '../adresseNominatim';

const LIRE = (p) => fs.readFileSync(path.join(__dirname, p), 'utf8');
const WIZARD = LIRE('../../components/dashboard/OfferWizard.js');
const DASHBOARD = LIRE('../../components/CoachDashboard.js');
const CHAMP = LIRE('../../components/dashboard/ChampAdresse.js');

const AUVERNIER = {
  place_id: 1, lat: '46.9765', lon: '6.8791',
  display_name: 'Bord du Lac, Auvernier, Neuchâtel, 2012, Suisse',
  address: { road: 'Bord du Lac', village: 'Auvernier', postcode: '2012',
             state: 'Neuchâtel', country: 'Suisse', country_code: 'ch' }
};
const LAUSANNE = {
  place_id: 2, lat: '46.5197', lon: '6.6323',
  display_name: 'Esplanade de Montbenon, Lausanne',
  address: { road: 'Esplanade de Montbenon', city: 'Lausanne',
             country: 'Suisse', country_code: 'ch' }
};

describe('R3a — la ville sort de la reponse OpenStreetMap', () => {
  test('Auvernier est un `village`, Lausanne une `city` — les deux sont lues', () => {
    expect(extraireVille(AUVERNIER)).toBe('Auvernier');
    expect(extraireVille(LAUSANNE)).toBe('Lausanne');
  });

  test("une reponse inexploitable ne casse rien", () => {
    [null, undefined, {}, 'texte', 42, { address: null }].forEach((x) => {
      expect(extraireVille(x)).toBe('');
    });
  });

  test('la ville n est JAMAIS deduite de la region', () => {
    // « Bord du Lac, Auvernier » est classe `region=neuchatel` cote Afroboost.
    // La commune reste Auvernier : c'est tout l'enjeu du lot.
    expect(extraireVille(AUVERNIER)).not.toBe('Neuchâtel');
    expect(AUVERNIER.address.state).toBe('Neuchâtel'); // la region, elle, dit ca
  });

  test('les coordonnees voyagent avec la proposition', () => {
    const [a] = normaliserReponse([AUVERNIER]);
    expect(a.lat).toBeCloseTo(46.9765);
    expect(a.lon).toBeCloseTo(6.8791);
    expect(a.ville).toBe('Auvernier');
  });

  test('une proposition sans coordonnees lisibles n en invente pas', () => {
    const [a] = normaliserReponse([{ ...AUVERNIER, lat: 'nan', lon: '' }]);
    expect(a.lat).toBeNull();
    expect(a.lon).toBeNull();
    // ... et surtout PAS zero : 0,0 est un point au large du Ghana.
    expect(a.lat).not.toBe(0);
  });
});

describe('U1b — aucune regression', () => {
  test('les trois champs historiques sont inchanges', () => {
    const [a] = normaliserReponse([AUVERNIER]);
    expect(a.cle).toBe('1');
    expect(a.libelle).toBe('Bord du Lac, 2012 Auvernier');
    expect(a.detail).toBe('Neuchâtel, Suisse');
  });

  test('`formaterAdresse` produit exactement ce qu il produisait', () => {
    expect(formaterAdresse(AUVERNIER)).toBe('Bord du Lac, 2012 Auvernier');
    expect(formaterAdresse(LAUSANNE)).toBe('Esplanade de Montbenon, Lausanne');
  });

  test('une reponse illisible reste une liste vide', () => {
    expect(normaliserReponse(null)).toEqual([]);
    expect(normaliserReponse('<html>503</html>')).toEqual([]);
  });

  test('le nouveau rappel est FACULTATIF — sans lui, rien ne change', () => {
    expect(CHAMP).toContain("if (typeof onChoisir === 'function') onChoisir(item);");
    // Appele APRES `onChange` : le texte est pose avant que quiconque reagisse.
    expect(CHAMP.indexOf('onChange(item.libelle)'))
      .toBeLessThan(CHAMP.indexOf('onChoisir(item)'));
  });
});

describe('R3a — le formulaire d offre', () => {
  test('un champ Ville existe, en francais, sans jargon', () => {
    expect(WIZARD).toContain('offer-city');
    expect(WIZARD).toMatch(/>\{' '\}Ville/);
    expect(WIZARD).not.toContain('location_city</label>');
  });

  test('choisir une adresse remplit ville et coordonnees', () => {
    expect(WIZARD).toContain("if (item.ville) set('location_city', item.ville);");
    expect(WIZARD).toContain("set('location_lat', item.lat);");
  });

  test('le champ adresse alimente la version structuree, sans double saisie', () => {
    expect(WIZARD).toContain("set('location_address', v);");
  });

  test('les quatre champs partent dans la requete', () => {
    ['location_city:', 'location_address:', 'location_lat:', 'location_lng:']
      .forEach((c) => expect(DASHBOARD).toContain(c));
  });

  test('... et sont RELUS a la reouverture — le piege des huit correctifs', () => {
    expect(DASHBOARD).toMatch(/location_city:\s*offer\.location_city/);
    expect(DASHBOARD).toMatch(/location_lat:\s*offer\.location_lat/);
  });

  test('une offre neuve n a ni ville ni coordonnees pre-remplies', () => {
    expect(DASHBOARD).toMatch(/location_city:\s*''/);
    expect(DASHBOARD).toMatch(/location_lat:\s*null/);
  });

  test('la ville est FACULTATIVE : rien ne bloque une offre sans lieu', () => {
    // Seuls le nom et le type bloquent l'enregistrement. Un abonnement ou un
    // t-shirt n'ont pas d'adresse, et le formulaire ne doit pas leur en
    // inventer une.
    const i = WIZARD.indexOf('const handleSave');
    const bloc = WIZARD.slice(i, i + 1600);
    expect(bloc).not.toContain('location_city');
    expect(bloc).not.toContain('location_address');
  });
});

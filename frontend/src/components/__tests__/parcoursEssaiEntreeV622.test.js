// V622 — LE NOUVEAU POINT D'ENTRÉE (page d'essai -> parcours EXISTANT).
//
// Ce fichier ne teste QUE ce qui a été ajouté : la page d'essai ouvre le même
// parcours que les Partenaires (`ParcoursPartenaire`) avec `parcours=essai`, et
// l'attribution reconnaît `eventfrog` et le vrai chemin d'atterrissage. Le
// parcours Partenaire, lui, doit s'ouvrir EXACTEMENT comme avant.
jest.mock('axios', () => ({ get: jest.fn(() => Promise.resolve({ data: {} })), post: jest.fn() }));
jest.mock('qrcode.react', () => ({ QRCodeSVG: () => null, QRCodeCanvas: () => null }));
import { lireParcoursPartenaire } from '../ParcoursPartenaire';
import { attributionDepuisUrl, cheminAtterrissage, SOURCES } from '../../utils/attribution';

describe('V622 — point d’entrée du parcours essai', () => {
  test('page d’essai : ?offre=&reserver=1&parcours=essai ouvre le parcours existant', () => {
    expect(lireParcoursPartenaire('?offre=c1e5&reserver=1&parcours=essai')).toEqual({ offre: 'c1e5' });
    expect(lireParcoursPartenaire('?offre=c1e5&reserver=1&parcours=essai&utm_source=eventfrog&utm_medium=referral'))
      .toEqual({ offre: 'c1e5' });
  });

  test('parcours Partenaire : strictement inchangé', () => {
    expect(lireParcoursPartenaire('?offre=c1e5&reserver=1&utm_source=partenaire&utm_medium=referral'))
      .toEqual({ offre: 'c1e5' });
  });

  test('sans offre, sans reserver=1, ou sans marqueur : aucun parcours (comme avant)', () => {
    expect(lireParcoursPartenaire('?reserver=1&parcours=essai')).toBeNull();
    expect(lireParcoursPartenaire('?offre=c1e5&parcours=essai')).toBeNull();
    expect(lireParcoursPartenaire('?offre=c1e5&reserver=1')).toBeNull();
    expect(lireParcoursPartenaire('?offre=c1e5&reserver=1&utm_source=instagram')).toBeNull();
    expect(lireParcoursPartenaire('?offre=c1e5&reserver=1&parcours=autre')).toBeNull();
    expect(lireParcoursPartenaire('?link=b83914b4-c5a')).toBeNull();
  });
});

describe('V622 — attribution : même système, deux corrections', () => {
  test('eventfrog est une source reconnue', () => {
    expect(SOURCES).toContain('eventfrog');
    const t = attributionDepuisUrl('?utm_source=eventfrog&utm_medium=referral&utm_campaign=test', '', '/');
    expect(t).toMatchObject({ source: 'eventfrog', medium: 'referral', campaign: 'test' });
  });

  test('landing_path = la page d’essai quand on en vient (referrer interne)', () => {
    const t = attributionDepuisUrl('?utm_source=eventfrog&utm_medium=referral&utm_campaign=test',
      'https://afroboost.com/cours-essai-gratuit-neuchatel?utm_source=eventfrog', '/');
    expect(t.landing_path).toBe('/cours-essai-gratuit-neuchatel');
    expect(cheminAtterrissage('https://www.afroboost.com/a-propos', '/')).toBe('/a-propos');
  });

  test('landing_path inchangé dans tous les autres cas', () => {
    expect(cheminAtterrissage('https://www.google.com/', '/')).toBe('/');
    expect(cheminAtterrissage('https://evil.example/cours-essai-gratuit-neuchatel', '/')).toBe('/');
    expect(cheminAtterrissage('https://afroboost.com/espace/AFR-123', '/')).toBe('/');
    expect(cheminAtterrissage('', '/coach/bassi')).toBe('/coach/bassi');
    expect(cheminAtterrissage('pas une url', '/')).toBe('/');
  });

  test('?ref= reste traduit en partenaire / referral, à part', () => {
    const t = attributionDepuisUrl('?ref=akoko', '', '/');
    expect(t).toMatchObject({ source: 'partenaire', medium: 'referral', content: 'akoko' });
  });
});

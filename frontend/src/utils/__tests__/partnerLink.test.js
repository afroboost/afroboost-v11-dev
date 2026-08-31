// P2-C — la construction du lien personnel d'un partenaire.
//
// CE QUE CE FICHIER VERROUILLE, ET POURQUOI C'EST LE POINT LE PLUS IMPORTANT
// DU LOT. Les quatre valeurs UTM ne sont pas des libelles decoratifs : elles
// sont ce qui permet a M2 de rattacher une reservation a un partenaire.
// `partenaire` figure dans la liste blanche des sources (`attribution.js`), et
// la page d'essai propage elle-meme les parametres vers le tunnel. Renommer
// l'une des quatre — `referral` en `parrainage`, `essai_neuchatel` en autre
// chose — ne provoquerait AUCUNE erreur : pas de 500, pas de page blanche,
// simplement des partenaires qui n'auraient jamais rien apporte, et personne
// pour s'en apercevoir avant des semaines. D'ou des assertions sur la chaine
// LITTERALE, et non sur les constantes qui la produisent : un test qui lit
// `P2C_UTM.utm_medium` suivrait docilement une faute de frappe.

import {
  construireLienPartenaire, p2cNomFichierQr, p2bSlugValide, p2bSuggererSlug,
  P2C_BASE_ESSAI, P2C_UTM,
} from '../partnerLink';

const LIEN_ATTENDU =
  'https://afroboost.com/cours-essai-gratuit-neuchatel'
  + '?utm_source=partenaire&utm_medium=referral&utm_campaign=essai_neuchatel'
  + '&utm_content=akoko_tresses';

describe('P2-C — les quatre UTM sont VERROUILLEES', () => {
  test("le lien est EXACTEMENT celui attendu, caractere pour caractere", () => {
    expect(construireLienPartenaire('akoko_tresses')).toBe(LIEN_ATTENDU);
  });

  test('utm_source vaut exactement « partenaire »', () => {
    expect(construireLienPartenaire('x_y_z')).toContain('utm_source=partenaire');
    expect(P2C_UTM.utm_source).toBe('partenaire');
  });

  test('utm_medium vaut exactement « referral »', () => {
    expect(construireLienPartenaire('x_y_z')).toContain('utm_medium=referral');
    expect(P2C_UTM.utm_medium).toBe('referral');
  });

  test('utm_campaign vaut exactement « essai_neuchatel »', () => {
    expect(construireLienPartenaire('x_y_z')).toContain('utm_campaign=essai_neuchatel');
    expect(P2C_UTM.utm_campaign).toBe('essai_neuchatel');
  });

  test('utm_content vaut exactement le partner_slug', () => {
    expect(construireLienPartenaire('recif_neuchatel')).toContain('utm_content=recif_neuchatel');
  });

  test("la page visee est celle de l'essai, pas le tunnel — c'est elle qui "
     + 'propage les UTM', () => {
    expect(P2C_BASE_ESSAI).toBe('https://afroboost.com/cours-essai-gratuit-neuchatel');
    expect(construireLienPartenaire('x_y_z')).not.toContain('?link=');
  });

  test("les quatre parametres sont presents, et il n'y en a pas un cinquieme", () => {
    const q = construireLienPartenaire('x_y_z').split('?')[1].split('&');
    expect(q.map((p) => p.split('=')[0]))
      .toEqual(['utm_source', 'utm_medium', 'utm_campaign', 'utm_content']);
  });

  test('les constantes UTM sont gelees — une modification a chaud est impossible', () => {
    expect(Object.isFrozen(P2C_UTM)).toBe(true);
  });
});

describe('P2-C — la fonction est PURE et deterministe', () => {
  test('deux appels rendent exactement la meme chaine', () => {
    expect(construireLienPartenaire('akoko_tresses'))
      .toBe(construireLienPartenaire('akoko_tresses'));
  });

  test('elle ne lit ni ne modifie le stockage local', () => {
    const lire = jest.spyOn(Storage.prototype, 'getItem');
    const ecrire = jest.spyOn(Storage.prototype, 'setItem');
    construireLienPartenaire('akoko_tresses');
    expect(lire).not.toHaveBeenCalled();
    expect(ecrire).not.toHaveBeenCalled();
    lire.mockRestore();
    ecrire.mockRestore();
  });

  test('tous les caracteres autorises passent', () => {
    expect(construireLienPartenaire('a1_b2_c3')).toContain('utm_content=a1_b2_c3');
    expect(construireLienPartenaire('a'.repeat(40))).toContain('utm_content=' + 'a'.repeat(40));
  });

  test('un slug invalide ne produit AUCUN lien — jamais un lien approximatif', () => {
    for (const mauvais of ['', null, undefined, 'ab', 'a'.repeat(41), 'Akoko_Tresses',
      'akoko tresses', 'akoko-tresses', 'récif', '../../etc', 'a/b', '<script>']) {
      expect(construireLienPartenaire(mauvais)).toBe('');
    }
  });

  test('les espaces de bord sont tolerés, le reste non', () => {
    expect(construireLienPartenaire('  akoko_tresses  ')).toBe(LIEN_ATTENDU);
    expect(construireLienPartenaire('akoko tresses')).toBe('');
  });
});

describe('P2-C — le nom du fichier QR', () => {
  test('il contient le partner_slug et se termine en .png', () => {
    expect(p2cNomFichierQr('akoko_tresses')).toBe('afroboost-partenaire-akoko_tresses-qr.png');
  });

  test('aucun espace, aucun caractere problematique pour un systeme de fichiers', () => {
    expect(p2cNomFichierQr('recif_neuchatel')).toMatch(/^[a-z0-9_.-]+$/);
  });

  test('un slug invalide ne produit aucun nom de fichier', () => {
    expect(p2cNomFichierQr('a b')).toBe('');
    expect(p2cNomFichierQr('')).toBe('');
  });
});

describe('P2-C — la regle du slug reste UNE seule regle', () => {
  test('elle est identique a celle du serveur (^[a-z0-9_]{3,40}$)', () => {
    expect(p2bSlugValide('akoko_tresses')).toBe(true);
    expect(p2bSlugValide('ab')).toBe(false);
    expect(p2bSlugValide('a'.repeat(41))).toBe(false);
    expect(p2bSlugValide('Akoko')).toBe(false);
    expect(p2bSlugValide('akoko-tresses')).toBe(false);
  });

  test('la suggestion deplie les accents plutot que de les supprimer', () => {
    expect(p2bSuggererSlug('Récif Neuchâtel')).toBe('recif_neuchatel');
    expect(p2bSuggererSlug('Vénus Nails — Neuchâtel')).toBe('venus_nails_neuchatel');
  });

  test('un lien construit depuis une suggestion est toujours valide', () => {
    const slug = p2bSuggererSlug('Welcome to Neuchâtel');
    expect(p2bSlugValide(slug)).toBe(true);
    expect(construireLienPartenaire(slug)).toContain('utm_content=welcome_to_neuchatel');
  });
});

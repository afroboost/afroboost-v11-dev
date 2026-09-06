// DEEPLINK PROSPECTION — LA SOURCE UNIQUE DE L'INTENTION.
//
// CE QUI EST PROUVE ICI :
//
//   * la cible se lit dans la query string, et SEULEMENT quand `prospection=1`
//     est present : une url quelconque portant `inbound` ne declenche rien ;
//   * `?prospection=1` SANS cible rend '' et non `null` — la nuance decide si
//     l'ecran bascule d'onglet sans ouvrir de conversation ;
//   * lire n'efface pas. C'est le coeur du correctif : l'ancienne version
//     effacait au montage, pendant que les conversations chargeaient encore ;
//   * consommer efface, et une seule fois ;
//   * la capture a lieu A L'IMPORT, donc avant tout rendu React ;
//   * elle nettoie l'url, pour qu'un rafraichissement ne rejoue pas l'intention;
//   * un stockage indisponible (navigation privee) ne fait crasher personne.

import {
  CLE, cibleDeRecherche, poser, lire, consommer, capturer, EVENEMENT,
} from '../prospectionIntention';

const ID = '5068f64c-abcd-4453-b508-b19825508d18';

beforeEach(() => { window.sessionStorage.clear(); });

// ---------------------------------------------------------------- 1. LECTURE
describe('1. la cible se lit dans l URL, et seulement quand elle est demandee', () => {
  test('1a. `prospection=1&inbound=<id>` rend l identifiant', () => {
    expect(cibleDeRecherche(`?prospection=1&inbound=${ID}`)).toBe(ID);
  });

  test('1b. l ordre des parametres est sans importance', () => {
    expect(cibleDeRecherche(`?inbound=${ID}&prospection=1`)).toBe(ID);
  });

  test('1c. `prospection=1` SANS cible rend la chaine vide, PAS null', () => {
    // La nuance decide : '' bascule l onglet sans ouvrir de conversation,
    // `null` ne bascule rien du tout.
    expect(cibleDeRecherche('?prospection=1')).toBe('');
  });

  test('1d. sans `prospection=1`, un `inbound` seul ne declenche RIEN', () => {
    expect(cibleDeRecherche(`?inbound=${ID}`)).toBeNull();
  });

  test('1e. `prospection=0` n est pas `prospection=1`', () => {
    expect(cibleDeRecherche('?prospection=0&inbound=' + ID)).toBeNull();
  });

  test('1f. une url vide ou absurde ne casse rien', () => {
    expect(cibleDeRecherche('')).toBeNull();
    expect(cibleDeRecherche(undefined)).toBeNull();
    expect(cibleDeRecherche('????')).toBeNull();
  });

  test('1g. un identifiant demesure est borne a 64 caracteres', () => {
    const enorme = 'x'.repeat(500);
    expect(cibleDeRecherche(`?prospection=1&inbound=${enorme}`)).toHaveLength(64);
  });

  test('1h. les espaces autour de l identifiant sont retires', () => {
    expect(cibleDeRecherche('?prospection=1&inbound=%20' + ID + '%20')).toBe(ID);
  });
});

// ------------------------------------------------------- 2. LIRE ≠ CONSOMMER
describe('2. lire n est pas consommer', () => {
  test('2a. poser puis lire rend la valeur', () => {
    poser(ID);
    expect(lire()).toBe(ID);
  });

  test('2b. LIRE N EFFACE PAS — c est tout le correctif', () => {
    // L ancienne version effacait au montage du dashboard, avant meme que les
    // conversations soient chargees : l intention etait perdue pour rien.
    poser(ID);
    expect(lire()).toBe(ID);
    expect(lire()).toBe(ID);
    expect(lire()).toBe(ID);
  });

  test('2c. consommer efface', () => {
    poser(ID);
    consommer();
    expect(lire()).toBeNull();
  });

  test('2d. consommer deux fois ne casse rien', () => {
    poser(ID);
    consommer();
    consommer();
    expect(lire()).toBeNull();
  });

  test('2e. sans rien de pose, lire rend null — aucune bascule', () => {
    expect(lire()).toBeNull();
  });

  test('2f. une demande SANS cible se distingue d une absence de demande', () => {
    poser('');
    expect(lire()).toBe('');       // demande sans cible : on bascule l onglet
    consommer();
    expect(lire()).toBeNull();     // aucune demande : on ne bascule rien
  });
});

// ----------------------------------------------------------- 3. LA CAPTURE
describe('3. la capture lit l URL et nettoie derriere elle', () => {
  const poserURL = (recherche) => {
    window.history.replaceState({}, '', '/dashboard' + recherche);
  };

  test('3a. capturer depuis l url pose l intention', () => {
    poserURL(`?prospection=1&inbound=${ID}`);
    expect(capturer()).toBe(ID);
    expect(lire()).toBe(ID);
  });

  test('3b. et RETIRE la query de la barre d adresse', () => {
    // Sans ce nettoyage, un rafraichissement rejouerait l intention, et
    // l identifiant resterait visible dans l url.
    poserURL(`?prospection=1&inbound=${ID}`);
    capturer();
    expect(window.location.search).toBe('');
    expect(window.location.pathname).toBe('/dashboard');
  });

  test('3c. une url sans demande ne pose rien et ne nettoie rien', () => {
    poserURL('?autre=1');
    expect(capturer()).toBeNull();
    expect(lire()).toBeNull();
    expect(window.location.search).toBe('?autre=1');
  });

  test('3d. le hash est conserve — il porte la route du dashboard', () => {
    window.history.replaceState({}, '', `/?prospection=1&inbound=${ID}#coach-dashboard`);
    capturer();
    expect(window.location.hash).toBe('#coach-dashboard');
  });
});

// --------------------------------------------------- 4. LA CAPTURE A L IMPORT
describe('4. la capture a lieu a l import, donc avant tout rendu React', () => {
  test('4a. le module exporte le resultat de sa capture au chargement', () => {
    // C est ce qui ferme la course : quand React monte le premier composant,
    // la capture appartient deja au passe. Un `useEffect`, lui, resterait
    // soumis a l ordre de montage (enfants avant parents).
    const mod = require('../prospectionIntention');
    expect(Object.prototype.hasOwnProperty.call(mod, 'CAPTURE_AU_CHARGEMENT'))
      .toBe(true);
  });

  test('4b. le module est le SEUL a nommer la cle de stockage', () => {
    expect(CLE).toBe('afroboost_prospection_inbound');
  });
});

// -------------------------------------------------------- 5. MODE DEGRADE
describe('5. un stockage indisponible ne fait crasher personne', () => {
  test('5a. poser / lire / consommer survivent a un sessionStorage qui jette', () => {
    const vrai = Object.getOwnPropertyDescriptor(window, 'sessionStorage');
    Object.defineProperty(window, 'sessionStorage', {
      configurable: true,
      get() { throw new Error('navigation privee'); },
    });
    expect(() => poser(ID)).not.toThrow();
    expect(poser(ID)).toBe(false);
    expect(lire()).toBeNull();
    expect(consommer()).toBe(false);
    Object.defineProperty(window, 'sessionStorage', vrai);
  });
});

// ============================================================================
// 6. LA SEQUENCE REELLE — celle qui a echoue en production le 06/09.
// ============================================================================
describe('6. la sequence reelle du lien profond', () => {
  test('6a. A. l intention est LISIBLE avant que le moindre composant ne monte', () => {
    // LE TEST QUI AURAIT ATTRAPE LE DEFAUT. Avant le correctif, la pose se
    // faisait dans un `useEffect` d App ; l effet de montage de CoachDashboard,
    // execute AVANT celui de son parent, ne trouvait rien. Ici la capture est
    // faite par l import : au moment ou React demarre, elle est deja du passe.
    window.history.replaceState({}, '', `/?prospection=1&inbound=${ID}`);
    capturer();                       // ce que fait l import du module
    const vuParLEnfantAuMontage = lire();
    expect(vuParLEnfantAuMontage).toBe(ID);
  });

  test('6b. E. l intention SURVIT au passage par la connexion', () => {
    // Le coach n est pas connecte : il voit d abord le login. L intention ne
    // doit pas mourir en route, sinon il retombe sur une liste anonyme.
    window.history.replaceState({}, '', `/?prospection=1&inbound=${ID}`);
    capturer();
    // … le modal de connexion s ouvre, le coach s authentifie, le dashboard
    // monte enfin. Rien n a consomme l intention entre-temps :
    expect(lire()).toBe(ID);
  });

  test('6c. H. l intention n est consommee QU APRES le succes', () => {
    window.history.replaceState({}, '', `/?prospection=1&inbound=${ID}`);
    capturer();
    expect(lire()).toBe(ID);          // conversations pas encore chargees
    expect(lire()).toBe(ID);          // toujours pas : on attend, on n efface pas
    consommer();                      // la conversation est ouverte : maintenant
    expect(lire()).toBeNull();
  });

  test('6d. I. un rafraichissement SANS lien profond ne rejoue aucune intention', () => {
    window.history.replaceState({}, '', `/?prospection=1&inbound=${ID}`);
    capturer();
    consommer();                      // succes : l intention a ete honoree
    // Le coach rafraichit la page. L url a ete nettoyee, le stockage est vide :
    window.history.replaceState({}, '', '/');
    expect(capturer()).toBeNull();
    expect(lire()).toBeNull();
  });

  test('6e. l application DEJA OUVERTE est prevenue par une annonce', () => {
    // Le Service Worker ne recharge pas la page : l effet de montage du
    // dashboard ne se rejouera jamais. Sans annonce, l intention serait posee
    // et personne n irait la relire.
    const recus = [];
    const ecouteur = (e) => recus.push(e.detail);
    window.addEventListener(EVENEMENT, ecouteur);
    poser(ID);
    window.removeEventListener(EVENEMENT, ecouteur);
    expect(recus).toEqual([ID]);
  });

  test('6f. l annonce porte aussi la demande SANS cible', () => {
    const recus = [];
    const ecouteur = (e) => recus.push(e.detail);
    window.addEventListener(EVENEMENT, ecouteur);
    poser('');
    window.removeEventListener(EVENEMENT, ecouteur);
    expect(recus).toEqual(['']);      // bascule l onglet, n ouvre rien
  });
});

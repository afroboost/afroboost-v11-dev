/**
 * C9-B — tests de l'identite analytique.
 *
 * HORS LIGNE. `window.posthog` est un espion : aucun evenement ne part, aucune
 * fusion n'est produite. C'est indispensable ici — une fusion PostHog est
 * IRREVERSIBLE, un test qui en declencherait une ne serait pas rattrapable.
 *
 * Aucune dependance ajoutee : jest + jsdom viennent de react-scripts, et le
 * module teste est du JS pur (ni React, ni reseau). @testing-library est absent
 * du projet et le reste.
 */
import fs from 'fs';
import path from 'path';
import {
  c9bIdentifier, c9bCoupeCircuit, c9bSessionCoach,
  C9B_FORMAT, C9B_EMAILS_COACH
} from '../analyticsIdentity';

// Version du SDK analysee ligne a ligne pendant le pre-flight C9-B (sources
// extraites du sourcemap du bundle reellement servi). Les tests ci-dessous ne
// dependent d'AUCUN comportement interne de cette version : c'est notre code qui
// court-circuite les cas, pas le SDK. Cette constante n'est qu'un reperage.
const SDK_ANALYSE = '1.417.0';

const ID_A = 'a'.repeat(32);
const ID_B = 'b'.repeat(32);
const ID_REEL = '4cd05bbc4e6e69c533d5ce1ffbb68ef7';   // forme d'un vrai posthog_id

let ph;

beforeEach(() => {
  localStorage.clear();
  ph = {
    identify: jest.fn(),
    reset: jest.fn(),
    set_config: jest.fn(),
    get_distinct_id: jest.fn(() => '01920000-7000-7000-8000-000000000000') // UUID anonyme
  };
  window.posthog = ph;
});

afterEach(() => { delete window.posthog; });

// --------------------------------------------------------------------------
describe('format du pseudonyme', () => {
  test('accepte exactement 32 hexadecimaux minuscules', () => {
    expect(C9B_FORMAT.test(ID_REEL)).toBe(true);
    expect(C9B_FORMAT.test(ID_A)).toBe(true);
  });

  test('rejette un UUID anonyme de PostHog', () => {
    // C'est ce qui permet de distinguer « anonyme » de « deja identifie par nous »
    // sans lire le moindre interne du SDK.
    expect(C9B_FORMAT.test('01920000-7000-7000-8000-000000000000')).toBe(false);
  });
});

// --------------------------------------------------------------------------
describe('cas 10 — navigateur anonyme, identite valide', () => {
  test('identifie, et rattache donc la visite anterieure', () => {
    expect(c9bIdentifier(ID_REEL, { actif: true })).toBe('identifie');
    expect(ph.identify).toHaveBeenCalledTimes(1);
    expect(ph.identify).toHaveBeenCalledWith(ID_REEL);
    expect(ph.reset).not.toHaveBeenCalled();
  });

  test('identify recoit UN SEUL argument — aucune propriete de personne', () => {
    c9bIdentifier(ID_REEL, { actif: true });
    expect(ph.identify.mock.calls[0]).toHaveLength(1);
  });
});

// --------------------------------------------------------------------------
describe('cas 11 — meme identite deja posee', () => {
  test('idempotent : aucun appel, ni identify ni reset', () => {
    ph.get_distinct_id = jest.fn(() => ID_REEL);
    expect(c9bIdentifier(ID_REEL, { actif: true })).toBe('idempotent');
    expect(ph.identify).not.toHaveBeenCalled();
    expect(ph.reset).not.toHaveBeenCalled();
  });

  test('rejouable : dix appels ne produisent toujours rien', () => {
    ph.get_distinct_id = jest.fn(() => ID_REEL);
    for (let i = 0; i < 10; i += 1) c9bIdentifier(ID_REEL, { actif: true });
    expect(ph.identify).not.toHaveBeenCalled();
  });

  test('cas 18 — l\'idempotence ne repose PAS sur le SDK', () => {
    // Le SDK 1.417.0 n'emet rien sur un identify au meme id, mais c'est un
    // comportement de version, non un contrat : `/static/array.js` est un
    // pointeur mouvant. On court-circuite donc nous-memes, en amont.
    ph.get_distinct_id = jest.fn(() => ID_REEL);
    c9bIdentifier(ID_REEL, { actif: true });
    expect(ph.identify).not.toHaveBeenCalled();
    expect(typeof SDK_ANALYSE).toBe('string');
  });
});

// --------------------------------------------------------------------------
describe('cas 12 — personne A puis personne B sur le meme navigateur', () => {
  test('reset() AVANT identify(B), jamais l\'inverse', () => {
    ph.get_distinct_id = jest.fn(() => ID_A);
    expect(c9bIdentifier(ID_B, { actif: true })).toBe('change');
    expect(ph.reset).toHaveBeenCalledTimes(1);
    expect(ph.identify).toHaveBeenCalledTimes(1);
    expect(ph.identify).toHaveBeenCalledWith(ID_B);
    // L'ordre est la seule chose qui empeche la fusion de A dans B.
    expect(ph.reset.mock.invocationCallOrder[0])
      .toBeLessThan(ph.identify.mock.invocationCallOrder[0]);
  });

  test('aucun reset preventif sur un navigateur anonyme', () => {
    // Un reset ici detruirait l'identifiant anonyme, donc l'historique meme
    // qu'on cherche a rattacher.
    c9bIdentifier(ID_B, { actif: true });
    expect(ph.reset).not.toHaveBeenCalled();
  });
});

// --------------------------------------------------------------------------
describe('cas 6 et 7 — coach et admin', () => {
  const signaux = [
    ['afroboost_jwt', 'eyJhbGciOiJIUzI1NiJ9.charge.signature'],
    ['afroboost_coach_mode', 'true'],
    ['afroboost_coach_user', '{"email":"x@y.z"}'],
    ['afroboost_admin_persist', '1']
  ];

  signaux.forEach(([cle, val]) => {
    test(`aucun identify quand ${cle} est pose`, () => {
      localStorage.setItem(cle, val);
      expect(c9bIdentifier(ID_REEL, { actif: true })).toBe('coach');
      expect(ph.identify).not.toHaveBeenCalled();
      expect(ph.reset).not.toHaveBeenCalled();
    });
  });

  C9B_EMAILS_COACH.forEach((mail) => {
    test(`aucun identify pour l'adresse ${mail}, meme sur navigateur vierge`, () => {
      expect(c9bIdentifier(ID_REEL, { actif: true, email: mail })).toBe('coach');
      expect(ph.identify).not.toHaveBeenCalled();
    });
  });

  test('la casse et les espaces ne contournent pas le filtre', () => {
    expect(c9bIdentifier(ID_REEL, { actif: true, email: '  Contact.ArtBoost@Gmail.COM ' })).toBe('coach');
    expect(ph.identify).not.toHaveBeenCalled();
  });

  test('un abonne ordinaire n\'est pas pris pour un coach', () => {
    expect(c9bSessionCoach('ana@exemple.ch')).toBe(false);
    expect(c9bIdentifier(ID_REEL, { actif: true, email: 'ana@exemple.ch' })).toBe('identifie');
  });
});

// --------------------------------------------------------------------------
describe('cas 8, 9 et 20 — identifiant absent, malforme, ou erreur API', () => {
  const mauvais = [
    ['absent', undefined], ['nul', null], ['vide', ''], ['espaces', '   '],
    ['nombre', 12345], ['objet', {}], ['tableau', []], ['booleen', true],
    ['trop court', 'a'.repeat(31)], ['trop long', 'a'.repeat(33)],
    ['majuscules', 'A'.repeat(32)], ['non hexadecimal', 'z'.repeat(32)],
    ['UUID a tirets', '01920000-7000-7000-8000-000000000000'],
    ['espace en tete', ' ' + 'a'.repeat(32)]
  ];

  mauvais.forEach(([nom, valeur]) => {
    test(`${nom} -> aucune fusion`, () => {
      expect(c9bIdentifier(valeur, { actif: true })).toBe('identifiant-invalide');
      expect(ph.identify).not.toHaveBeenCalled();
      expect(ph.reset).not.toHaveBeenCalled();
    });
  });

  test('un objet ne provoque aucune TypeError remontee a l\'appelant', () => {
    // Le SDK, lui, ferait `value.toLowerCase()` sur l'objet et leverait.
    expect(() => c9bIdentifier({ ruse: true }, { actif: true })).not.toThrow();
  });
});

// --------------------------------------------------------------------------
describe('cas 13 et 14 — coupe-circuit', () => {
  test('eteint : aucun identify, aucun reset', () => {
    expect(c9bIdentifier(ID_REEL, { actif: false })).toBe('coupe-circuit');
    expect(ph.identify).not.toHaveBeenCalled();
    expect(ph.reset).not.toHaveBeenCalled();
  });

  test('eteint : coupe le traitement des personnes, meme deja identifie', () => {
    c9bCoupeCircuit(false);
    expect(ph.set_config).toHaveBeenCalledWith({ person_profiles: 'never' });
  });

  test('allume : revient au reglage nominal, jamais a autre chose', () => {
    c9bCoupeCircuit(true);
    expect(ph.set_config).toHaveBeenCalledWith({ person_profiles: 'identified_only' });
  });

  test('allume : le comportement attendu reprend', () => {
    expect(c9bIdentifier(ID_REEL, { actif: true })).toBe('identifie');
    expect(ph.identify).toHaveBeenCalledWith(ID_REEL);
  });

  test('le coupe-circuit prime sur tout le reste, y compris un id valide', () => {
    ph.get_distinct_id = jest.fn(() => ID_A);
    expect(c9bIdentifier(ID_B, { actif: false })).toBe('coupe-circuit');
    expect(ph.reset).not.toHaveBeenCalled();
  });
});

// --------------------------------------------------------------------------
describe('cas 19 — une panne de mesure ne casse jamais le parcours', () => {
  test('PostHog absent (bloqueur de publicite)', () => {
    delete window.posthog;
    expect(() => c9bIdentifier(ID_REEL, { actif: true })).not.toThrow();
    expect(c9bIdentifier(ID_REEL, { actif: true })).toBe('posthog-indisponible');
  });

  test('identify qui leve', () => {
    ph.identify = jest.fn(() => { throw new Error('boum'); });
    expect(c9bIdentifier(ID_REEL, { actif: true })).toBe('erreur');
  });

  test('get_distinct_id qui leve -> on renonce, on n\'identifie pas', () => {
    ph.get_distinct_id = jest.fn(() => { throw new Error('boum'); });
    expect(c9bIdentifier(ID_REEL, { actif: true })).toBe('sdk-non-charge');
    expect(ph.identify).not.toHaveBeenCalled();
  });

  test('set_config absent', () => {
    delete ph.set_config;
    expect(c9bCoupeCircuit(true)).toBe(false);
  });

  test('localStorage indisponible (navigation privee)', () => {
    const vrai = Object.getOwnPropertyDescriptor(window, 'localStorage');
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get() { throw new Error('acces refuse'); }
    });
    expect(() => c9bIdentifier(ID_REEL, { actif: true })).not.toThrow();
    Object.defineProperty(window, 'localStorage', vrai);
  });
});

// --------------------------------------------------------------------------
describe('SDK pas encore charge — le piege du stub', () => {
  // Le snippet pose en <head> installe un STUB dont toutes les methodes empilent
  // l'appel et renvoient `undefined`. Sans garde, on croirait le navigateur
  // anonyme et on identifierait sans `reset()` ; le vrai SDK rejouerait ensuite
  // la file avec l'identifiant persiste de la personne PRECEDENTE, et fusionnerait
  // l'ancienne dans la nouvelle. C'est le scenario le plus couteux du lot.
  const stub = () => ({
    identify: jest.fn(),
    reset: jest.fn(),
    set_config: jest.fn(),
    get_distinct_id: jest.fn(() => undefined)   // exactement ce que fait le stub
  });

  test('aucun identify tant que le SDK n\'a pas repondu', () => {
    window.posthog = stub();
    expect(c9bIdentifier(ID_REEL, { actif: true })).toBe('sdk-non-charge');
    expect(window.posthog.identify).not.toHaveBeenCalled();
    expect(window.posthog.reset).not.toHaveBeenCalled();
  });

  test('idem si get_distinct_id rend une chaine vide', () => {
    window.posthog = stub();
    window.posthog.get_distinct_id = jest.fn(() => '');
    expect(c9bIdentifier(ID_REEL, { actif: true })).toBe('sdk-non-charge');
    expect(window.posthog.identify).not.toHaveBeenCalled();
  });

  test('des que le vrai SDK repond, l\'identification reprend', () => {
    window.posthog = stub();
    window.posthog.get_distinct_id = jest.fn(() => '01920000-7000-7000-8000-000000000000');
    expect(c9bIdentifier(ID_REEL, { actif: true })).toBe('identifie');
    expect(window.posthog.identify).toHaveBeenCalledWith(ID_REEL);
  });

  test('renoncer coute une mesure, jamais une fusion', () => {
    // Le navigateur portait deja l'identite de A. Le stub masque cet etat : on
    // doit s'abstenir, surtout pas identifier B.
    window.posthog = stub();
    expect(c9bIdentifier(ID_B, { actif: true })).toBe('sdk-non-charge');
    expect(window.posthog.identify).not.toHaveBeenCalled();
  });
});

// --------------------------------------------------------------------------
describe('cas 15 — aucune donnee personnelle vers PostHog', () => {
  test('rien de ce qui est interdit n\'apparait dans les arguments', () => {
    const sentinelles = {
      email: 'c9b-sentinelle@exemple.test',
      prenom: 'Zoe-SENTINELLE-7f3',
      whatsapp: '+41760000001',
      code: 'AFR-SENTINEL',
      jwt: 'eyJKWT-SENTINELLE-7f3',
      reponse: 'REPONSE-SENTINELLE-7f3'
    };
    localStorage.setItem('afroboost_profile', JSON.stringify(sentinelles));
    c9bIdentifier(ID_REEL, { actif: true, email: sentinelles.email });
    c9bCoupeCircuit(true);

    const tout = JSON.stringify([
      ph.identify.mock.calls, ph.reset.mock.calls, ph.set_config.mock.calls
    ]);
    Object.values(sentinelles).forEach((s) => expect(tout).not.toContain(s));
    expect(tout).not.toContain('@');
    expect(tout).not.toContain('AFR-');
  });

  test('l\'e-mail sert au filtre coach mais ne sort jamais', () => {
    c9bIdentifier(ID_REEL, { actif: true, email: 'ana@exemple.ch' });
    expect(JSON.stringify(ph.identify.mock.calls)).not.toContain('ana');
  });
});

// --------------------------------------------------------------------------
describe('cas 16 et 17 — garanties de source', () => {
  const RACINE = path.join(__dirname, '..', '..', '..');   // -> frontend/

  // Les fichiers de test sont exclus : celui-ci contient volontairement les
  // motifs interdits (c'est son objet), il s'auto-detecterait sinon. Ce qui est
  // audite, c'est le code EXPEDIE au navigateur — les tests n'y sont jamais.
  const fichiersJs = (dir) => {
    const pile = [dir]; const trouves = [];
    while (pile.length) {
      const p = pile.pop();
      for (const e of fs.readdirSync(p, { withFileTypes: true })) {
        const f = path.join(p, e.name);
        if (e.isDirectory()) { if (e.name !== 'node_modules' && e.name !== '__tests__') pile.push(f); }
        else if (/\.(js|jsx)$/.test(e.name) && !/\.backup/.test(e.name) && !/\.test\.js$/.test(e.name)) {
          trouves.push(f);
        }
      }
    }
    return trouves;
  };

  // Le sel est cite dans les COMMENTAIRES du module (pour expliquer d'ou vient le
  // pseudonyme). Ce qui doit etre absent, c'est du CODE qui le lise ou le rejoue.
  const sansCommentaires = (src) => src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1');

  test('cas 16 — le sel n\'atteint jamais le navigateur', () => {
    const cibles = fichiersJs(path.join(RACINE, 'src'))
      .concat([path.join(RACINE, 'public', 'index.html')]);
    cibles.forEach((f) => {
      expect(sansCommentaires(fs.readFileSync(f, 'utf8'))).not.toMatch(/POSTHOG_ID_SALT|afroboost-c9/);
    });
  });

  test('cas 16 bis — aucun hachage recalcule dans le module d\'identite', () => {
    const src = sansCommentaires(
      fs.readFileSync(path.join(RACINE, 'src', 'utils', 'analyticsIdentity.js'), 'utf8')
    );
    expect(src).not.toMatch(/sha256|crypto\.subtle|createHash/i);
  });

  test('cas 17 — identify() et reset() ne vivent que dans ce module', () => {
    // ⚠️ Le motif doit voir les appels PAR ALIAS. Le module fait `const ph =
    // c9bPostHog()` puis `ph.identify(...)` : un motif ancre sur le litteral
    // `posthog.identify(` ne les verrait PAS, et passerait au vert grace aux
    // seules mentions en commentaire — un garde qui ne garde rien. On strippe
    // donc les commentaires, et on cherche l'appel quel que soit le porteur.
    const SEUL = path.join(RACINE, 'src', 'utils', 'analyticsIdentity.js');

    const identifiants = fichiersJs(path.join(RACINE, 'src'))
      .filter((f) => /\.\s*identify\s*\(/.test(sansCommentaires(fs.readFileSync(f, 'utf8'))));
    expect(identifiants).toEqual([SEUL]);

    const reseteurs = fichiersJs(path.join(RACINE, 'src'))
      // `e.target.reset()` sur un formulaire est un faux positif connu
      // (CoachDashboard.js) : on n'accepte que les porteurs PostHog.
      .filter((f) => /\b(ph|posthog|window\.posthog)\s*\.\s*reset\s*\(/
        .test(sansCommentaires(fs.readFileSync(f, 'utf8'))));
    expect(reseteurs).toEqual([SEUL]);
  });

  test('cas 17 ter — le garde de source mord vraiment', () => {
    // Preuve que le motif ci-dessus attrape la forme REELLEMENT employee dans le
    // module (appel par alias), et pas seulement le litteral `posthog.identify(`.
    const nu = sansCommentaires(fs.readFileSync(
      path.join(RACINE, 'src', 'utils', 'analyticsIdentity.js'), 'utf8'));
    expect(/\bph\s*\.\s*identify\s*\(/.test(nu)).toBe(true);
    expect(/posthog\s*\.\s*identify\s*\(/.test(nu)).toBe(false);
  });

  test('cas 17 bis — un seul appelant, et il est dans ChatWidget', () => {
    const appelants = fichiersJs(path.join(RACINE, 'src'))
      .filter((f) => /c9bIdentifier\s*\(/.test(fs.readFileSync(f, 'utf8')))
      .filter((f) => !f.endsWith('analyticsIdentity.js') && !/__tests__/.test(f));
    expect(appelants).toEqual([path.join(RACINE, 'src', 'components', 'ChatWidget.js')]);
  });

  test('la liste des adresses coach reste alignee sur celle de ChatWidget', () => {
    // Elle y est dupliquee (COACH_EMAILS). Une divergence rouvrirait la porte a
    // l'identification du proprietaire comme prospect.
    const cw = fs.readFileSync(path.join(RACINE, 'src', 'components', 'ChatWidget.js'), 'utf8');
    C9B_EMAILS_COACH.forEach((mail) => expect(cw).toContain(mail));
  });
});

// V670 — Les briques qui rendent le choix de langue FIABLE : un code toujours valide,
// un choix qui survit, des dates qui n'inventent aucun mot.
import {
  CLE_LANGUE, normaliserLangue, lireLangue, ecrireLangue, appliquerLangueDocument,
  localeDates, formaterDate, nomsJoursSemaine, viderStockagesSaufLangue,
} from '../langue';
import { TRANSLATE_LANGS, CODES_LANGUES, STATUT_LANGUE, getLangue } from '../../config/translateLangs';

// Un « localStorage » en mémoire, dont on peut simuler la panne.
function faux(contenu = {}, { panne = false } = {}) {
  const d = { ...contenu };
  return {
    clear: () => { if (panne) throw new Error('SecurityError'); Object.keys(d).forEach((k) => delete d[k]); },
    getItem: (k) => { if (panne) throw new Error('SecurityError'); return Object.prototype.hasOwnProperty.call(d, k) ? d[k] : null; },
    setItem: (k, v) => { if (panne) throw new Error('QuotaExceededError'); d[k] = String(v); },
    _d: d,
  };
}

describe('Les neuf langues du site — codes techniques', () => {
  it('ce sont exactement fr, en, de, ln, wo, sw, bm, bas, ht', () => {
    expect(CODES_LANGUES).toEqual(['fr', 'en', 'de', 'ln', 'wo', 'sw', 'bm', 'bas', 'ht']);
  });

  it('le sigle visible diffère du code pour le bassa (BA/bas) et le créole (CR/ht)', () => {
    expect(getLangue('bas').label).toBe('BA');
    expect(getLangue('ht').label).toBe('CR');
  });

  it('chaque langue a un nom complet lisible, une locale et un statut déclaré', () => {
    TRANSLATE_LANGS.forEach((l) => {
      expect(l.fullName.length).toBeGreaterThan(2);
      expect(l.locale).toBeTruthy();
      expect(Object.keys(STATUT_LANGUE)).toContain(l.status);
    });
  });

  it('les langues à faibles ressources ne se présentent JAMAIS comme complètes', () => {
    ['ln', 'wo', 'bm', 'bas'].forEach((c) => expect(getLangue(c).status).toBe('partial'));
    ['sw', 'ht'].forEach((c) => expect(getLangue(c).status).toBe('draft'));
    // Le visiteur lit un mot honnête à côté de ces langues.
    expect(STATUT_LANGUE.partial.etiquette).toBeTruthy();
    expect(STATUT_LANGUE.draft.etiquette).toBeTruthy();
  });
});

describe('normaliserLangue — toujours un code valide', () => {
  it.each([
    ['fr', 'fr'], ['EN', 'en'], ['de', 'de'], ['bas', 'bas'], ['ht', 'ht'],
    ['en-GB', 'en'], ['fr_CH', 'fr'], ['de-CH', 'de'], [' sw ', 'sw'],
  ])('%s → %s', (entree, attendu) => expect(normaliserLangue(entree)).toBe(attendu));

  it('ramène les sigles visibles au code technique (BA → bas, CR → ht)', () => {
    expect(normaliserLangue('BA')).toBe('bas');
    expect(normaliserLangue('CR')).toBe('ht');
  });

  it.each([[null], [undefined], [''], ['  '], [42], [{}], ['klingon'], ['xx-YY']])(
    'une valeur invalide (%p) donne le français, jamais « undefined »',
    (v) => expect(normaliserLangue(v)).toBe('fr'),
  );
});

describe('Persistance du choix', () => {
  it('le choix est mémorisé puis relu (rechargement, visite suivante)', () => {
    const s = faux();
    expect(ecrireLangue('sw', s)).toBe('sw');
    expect(s._d[CLE_LANGUE]).toBe('sw');
    expect(lireLangue(s)).toBe('sw');
  });

  it('on mémorise le CODE TECHNIQUE même si on reçoit le sigle visible', () => {
    const s = faux();
    ecrireLangue('BA', s);
    expect(s._d[CLE_LANGUE]).toBe('bas');
  });

  it('une valeur corrompue dans le stockage ne casse rien : français', () => {
    expect(lireLangue(faux({ [CLE_LANGUE]: 'n\'importe quoi' }))).toBe('fr');
    expect(lireLangue(faux({ [CLE_LANGUE]: '' }))).toBe('fr');
  });

  it('un stockage indisponible (navigation privée, quota) ne lève aucune exception', () => {
    const s = faux({}, { panne: true });
    expect(() => lireLangue(s)).not.toThrow();
    expect(lireLangue(s)).toBe('fr');
    expect(() => ecrireLangue('de', s)).not.toThrow();
    expect(ecrireLangue('de', s)).toBe('de');     // le choix vaut pour la session
  });

  it('l\'ancienne clé `af_lang` est conservée : les visiteurs existants gardent leur langue', () => {
    expect(CLE_LANGUE).toBe('af_lang');
    expect(lireLangue(faux({ af_lang: 'ln' }))).toBe('ln');
  });
});

describe('<html lang>', () => {
  it('annonce la langue de la page', () => {
    const doc = { documentElement: { attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } } };
    appliquerLangueDocument('de', doc);
    expect(doc.documentElement.attrs.lang).toBe('de');
    appliquerLangueDocument('BA', doc);
    expect(doc.documentElement.attrs.lang).toBe('bas');
  });

  it('sans document (rendu serveur, test) : ne plante pas', () => {
    expect(() => appliquerLangueDocument('fr', null)).not.toThrow();
  });
});

describe('Dates — la fiabilité d\'une réservation avant tout', () => {
  // Mardi 3 novembre 2026, 12h UTC.
  const MARDI = new Date(Date.UTC(2026, 10, 3, 12));

  it('français, anglais, allemand : mêmes locales qu\'avant (aucune régression)', () => {
    expect(localeDates('fr')).toBe('fr-CH');
    expect(localeDates('en')).toBe('en-GB');
    expect(localeDates('de')).toBe('de-CH');
  });

  it('⚠️ une langue PARTIELLE garde la date en français (le reste de la phrase l\'est)', () => {
    ['ln', 'wo', 'bm', 'bas'].forEach((c) => expect(localeDates(c)).toBe('fr-CH'));
    expect(nomsJoursSemaine('wo')).toBeNull();
  });

  it('le kiswahili suit CLDR quand le navigateur le connaît, sinon le français', () => {
    const loc = localeDates('sw');
    expect(['sw', 'fr-CH']).toContain(loc);
  });

  it('le créole retombe en français si le navigateur n\'a pas ses données', () => {
    expect(['ht', 'fr-CH']).toContain(localeDates('ht'));
  });

  it('formaterDate : la même date, un nom de jour par langue, jamais une chaîne vide', () => {
    const o = { weekday: 'long', timeZone: 'UTC' };
    expect(formaterDate(MARDI, 'fr', o).toLowerCase()).toContain('mardi');
    expect(formaterDate(MARDI, 'en', o).toLowerCase()).toContain('tuesday');
    expect(formaterDate(MARDI, 'de', o).toLowerCase()).toContain('dienstag');
    ['sw', 'ln', 'wo', 'bm', 'bas', 'ht'].forEach((c) => {
      expect(formaterDate(MARDI, c, o).length).toBeGreaterThan(2);
    });
  });

  it('une date invalide ne plante pas : chaîne vide', () => {
    expect(formaterDate('pas une date', 'fr')).toBe('');
    expect(formaterDate(undefined, 'de')).toBe('');
  });

  it('nomsJoursSemaine : sept noms, dimanche d\'abord, dans le fuseau UTC', () => {
    const fr = nomsJoursSemaine('fr');
    expect(fr).toHaveLength(7);
    expect(fr[0].toLowerCase()).toContain('dimanche');
    expect(fr[2].toLowerCase()).toContain('mardi');
    expect(nomsJoursSemaine('en')[2].toLowerCase()).toContain('tuesday');
    expect(nomsJoursSemaine('de')[6].toLowerCase()).toContain('samstag');
  });
});

describe('Déconnexion — la langue survit', () => {
  it('⚠️ vider le stockage (déconnexion du chat) ne fait PAS perdre la langue choisie', () => {
    const local = faux({ af_lang: 'wo', afroboost_identity: 'x', afroboost_token: 'y' });
    const session = faux({ jeton: 'z' });
    expect(viderStockagesSaufLangue(local, session)).toBe('wo');
    expect(local._d).toEqual({ af_lang: 'wo' });         // tout le reste est bien effacé
    expect(session._d).toEqual({});
  });

  it('sans langue mémorisée : rien n\'est inventé, le français est écrit par défaut', () => {
    const local = faux({ autre: '1' });
    expect(viderStockagesSaufLangue(local, faux())).toBe('fr');
    expect(local._d).toEqual({ af_lang: 'fr' });
  });

  it('un stockage bloqué ne fait pas planter la déconnexion', () => {
    expect(() => viderStockagesSaufLangue(faux({}, { panne: true }), faux({}, { panne: true }))).not.toThrow();
  });

  it('aucun `localStorage.clear()` nu ne subsiste dans le chat (régression : la langue disparaissait)', () => {
    const fs = require('fs');
    const code = fs.readFileSync(require('path').join(__dirname, '..', '..', 'components', 'ChatWidget.js'), 'utf8');
    expect(code).not.toMatch(/localStorage\.clear\(\)/);
  });
});

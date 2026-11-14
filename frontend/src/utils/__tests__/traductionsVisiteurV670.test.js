// V670 — La qualité du DICTIONNAIRE lui-même : complétude, cohérence entre langues,
// honnêteté sur les langues à faibles ressources, et repli propre.
import {
  translations, couverture, fusionnerDictionnaire, fusionnerTable, interpoler, clesEnRepli, t, useTranslation,
} from '../i18n';
import { VISITEUR, VISITEUR_APP } from '../i18n-visiteur';
import { TRANSLATE_LANGS } from '../../config/translateLangs';
import { lireDictionnaireApp } from '../outils-i18n/lireDictionnaireApp';

const LANGUES_COMPLETES = ['en', 'de'];
const LANGUES_A_RELIRE = ['sw', 'ht'];
const LANGUES_PARTIELLES = ['ln', 'wo', 'bm', 'bas'];

const variables = (s) => [...s.matchAll(/\{([A-Za-z0-9_]+)\}/g)].map((m) => m[1]).sort();
const gras = (s) => (s.match(/\*\*/g) || []).length;
const emojis = (s) => (s.match(/\p{Extended_Pictographic}/gu) || []).join('');

describe('Table VISITEUR — complétude', () => {
  const cles = Object.keys(VISITEUR);

  it('couvre bien le parcours visiteur (plus de 100 clés)', () => {
    expect(cles.length).toBeGreaterThan(100);
  });

  it.each(['fr', ...LANGUES_COMPLETES, ...LANGUES_A_RELIRE])('chaque clé a une valeur « %s » non vide', (l) => {
    const vides = cles.filter((k) => typeof VISITEUR[k][l] !== 'string' || !VISITEUR[k][l].trim());
    expect(vides).toEqual([]);
  });

  it('aucune clé ne perd sa valeur française (le français affiché n\'a pas changé)', () => {
    expect(cles.filter((k) => translations.fr[k] !== VISITEUR[k].fr)).toEqual([]);
  });
});

describe('Table VISITEUR — cohérence entre langues', () => {
  const cles = Object.keys(VISITEUR);
  const langues = ['en', 'de', 'sw', 'ht'];

  it('⚠️ les {variables} sont IDENTIQUES dans toutes les langues (sinon : « {montant} » affiché)', () => {
    const fautes = [];
    cles.forEach((k) => {
      const ref = variables(VISITEUR[k].fr).join(',');
      langues.forEach((l) => {
        if (VISITEUR[k][l] && variables(VISITEUR[k][l]).join(',') !== ref) fautes.push(`${k}[${l}]`);
      });
    });
    expect(fautes).toEqual([]);
  });

  it('⚠️ les mots en gras (**…**) sont équilibrés et en même nombre que le français', () => {
    const fautes = [];
    cles.forEach((k) => {
      const ref = gras(VISITEUR[k].fr);
      expect(ref % 2).toBe(0);
      langues.forEach((l) => {
        if (VISITEUR[k][l] && gras(VISITEUR[k][l]) !== ref) fautes.push(`${k}[${l}]`);
      });
    });
    expect(fautes).toEqual([]);
  });

  it('les pictogrammes du français sont conservés (🛒 📅 📦 👇…) : rien ne disparaît en traduisant', () => {
    const fautes = [];
    cles.forEach((k) => {
      const ref = emojis(VISITEUR[k].fr);
      if (!ref) return;
      langues.forEach((l) => { if (emojis(VISITEUR[k][l]) !== ref) fautes.push(`${k}[${l}]`); });
    });
    expect(fautes).toEqual([]);
  });

  it('aucune traduction ne contient de balise HTML (le texte n\'est jamais interprété comme du HTML)', () => {
    cles.forEach((k) => langues.forEach((l) => expect(VISITEUR[k][l]).not.toMatch(/<[a-z/][^>]*>/i)));
  });
});

describe('⚠️ Langues à faibles ressources — jamais de phrase inventée', () => {
  it.each(LANGUES_PARTIELLES)('%s : la table visiteur ne contient que du VOCABULAIRE (≤ 2 mots par entrée)', (l) => {
    const entrees = Object.keys(VISITEUR).filter((k) => VISITEUR[k][l]);
    entrees.forEach((k) => expect(VISITEUR[k][l].trim().split(/\s+/).length).toBeLessThanOrEqual(2));
    expect(entrees.length).toBeLessThanOrEqual(6);
  });

  it.each(LANGUES_PARTIELLES)('%s : aucun jour de la semaine inventé dans VISITEUR_APP', (l) => {
    // Une date mal écrite fait manquer une séance : on garde le français.
    ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'].forEach((j) => {
      expect(VISITEUR_APP[j] && VISITEUR_APP[j][l]).toBeFalsy();
    });
  });

  it('wo.discoverCta (français + anglais mélangés) est retiré : le français vaut mieux', () => {
    expect(translations.wo.discoverCta).toBeUndefined();
    expect(t('discoverCta', 'wo')).toBe(t('discoverCta', 'fr'));
  });
});

describe('Repli — jamais de clé brute visible pour un texte qui existe en français', () => {
  it('une clé absente d\'une langue retombe sur le français', () => {
    expect(t('v_boutique', 'ln')).toBe('Boutique');
    expect(t('v_boutique', 'bas')).toBe('Boutique');
  });

  it('une langue inconnue retombe sur le français', () => {
    expect(t('v_boutique', 'klingon')).toBe('Boutique');
    expect(t('v_boutique', undefined)).toBe('Boutique');
  });

  it('une clé inexistante partout rend la clé (dernier recours), sans exception', () => {
    expect(t('cle_qui_n_existe_pas', 'de')).toBe('cle_qui_n_existe_pas');
  });

  it('les langues complètes ET à relire rendent bien leur propre texte', () => {
    expect(t('v_fermer', 'en')).toBe('Close');
    expect(t('v_fermer', 'de')).toBe('Schliessen');
    expect(t('v_fermer', 'sw')).toBe('Funga');
    expect(t('v_fermer', 'ht')).toBe('Fèmen');
  });

  it('mots de base des langues partielles (vocabulaire seulement)', () => {
    expect(t('v_fermer', 'ln')).toBe('Kokanga');
    expect(t('v_fermer', 'wo')).toBe('Tëj');
    expect(t('v_fermer', 'bm')).toBe('Datugu');
    expect(t('v_fermer', 'bas')).toBe('Fermer');              // rien d'inventé : français
  });

  it('les replis sont consignés pour le diagnostic, sans bruit en console', () => {
    t('v_boutique', 'bas');
    expect(clesEnRepli('bas')).toContain('v_boutique');
  });

  it('useTranslation suit la même règle, avec variables', () => {
    const { t: tt } = useTranslation('de');
    expect(tt('vm_places', { n: 12 })).toBe('12 Plätze');
  });
});

describe('Interpolation', () => {
  it('remplace {nom} par la valeur', () => {
    expect(interpoler('Total {n} x CHF {prix}', { n: 3, prix: '12.50' })).toBe('Total 3 x CHF 12.50');
  });
  it('une variable absente laisse {nom} visible — jamais « undefined »', () => {
    expect(interpoler('Total {n}', {})).toBe('Total {n}');
    expect(interpoler('Total {n}', { n: undefined })).toBe('Total {n}');
    expect(interpoler('Total {n}', { n: null })).toBe('Total {n}');
  });
  it('0 est une valeur valide', () => {
    expect(interpoler('{n} places', { n: 0 })).toBe('0 places');
  });
  it('sans variables : texte inchangé ; entrée non textuelle : inchangée', () => {
    expect(interpoler('Bonjour', undefined)).toBe('Bonjour');
    expect(interpoler(undefined, { n: 1 })).toBeUndefined();
  });
  it('pas d\'injection : les accolades de la valeur ne sont pas réinterprétées', () => {
    expect(interpoler('Code {c}', { c: '{n}' })).toBe('Code {n}');
  });
  it('chaque rendu français des clés à variables reste le texte d\'origine', () => {
    expect(t('vm_frais_de_port', 'fr', { montant: 5 })).toBe('Frais de port : CHF 5');
    expect(t('vm_tva', 'fr', { taux: 8.1 })).toBe('TVA 8.1%');
    expect(t('vm_places', 'fr', { n: 12 })).toBe('12 places');
    expect(t('vm_sous_total_quantite', 'fr', { n: 2, prix: '10.00' })).toBe('Sous-total (2 x CHF 10.00)');
  });
});

describe('Fusion des dictionnaires — un seul moteur', () => {
  it('fusionnerDictionnaire conserve la référence de chaque langue et fait gagner la source', () => {
    const cible = { fr: { a: 'A', b: 'B' }, sw: { a: 'a-sw' } };
    const refSw = cible.sw;
    fusionnerDictionnaire(cible, { fr: { a: 'A2', c: 'C' }, en: { a: 'en' } });
    expect(cible.fr).toEqual({ a: 'A2', b: 'B', c: 'C' });
    expect(cible.sw).toBe(refSw);
    expect(cible.en).toEqual({ a: 'en' });
  });

  it('fusionnerTable n\'écrit JAMAIS du français comme « traduction » ni une chaîne vide', () => {
    const cible = { fr: {}, en: {}, sw: {} };
    fusionnerTable(cible, { k: { fr: 'Zoom', en: 'Zoom', sw: '  ' }, j: { fr: 'Un', en: 'One', sw: 'Moja' } });
    expect(cible.fr).toEqual({ k: 'Zoom', j: 'Un' });
    expect(cible.en).toEqual({ j: 'One' });
    expect(cible.sw).toEqual({ j: 'Moja' });
  });

  it('le dictionnaire exporté est UN seul objet, vu par tout le monde', () => {
    // App.js fusionne son dictionnaire local DANS cet objet (cf. fusionnerDictionnaire).
    const local = lireDictionnaireApp();
    expect(Object.keys(local.fr).length).toBeGreaterThan(100);
    const copie = fusionnerDictionnaire(JSON.parse(JSON.stringify(translations)), local);
    // Les clés locales d'App.js l'emportent pour fr/en/de.
    expect(copie.fr.reservationConfirmed).toBe(local.fr.reservationConfirmed);
    // … et les 22 clés propres à i18n.js ne sont pas perdues.
    expect(copie.fr.seeProfile).toBe('Voir le profil');
  });
});

describe('Couverture du périmètre VISITEUR (dictionnaire fusionné, comme l\'App le voit)', () => {
  const local = lireDictionnaireApp();
  const fusion = fusionnerDictionnaire(JSON.parse(JSON.stringify(translations)), local);

  // Les clés que le visiteur peut réellement lire : la table visiteur, les clés visiteur
  // du dictionnaire d'App.js (VISITEUR_APP) et le vocabulaire de base de i18n.js.
  const BASE = ['loading', 'error', 'success', 'cancel', 'save', 'email', 'login', 'logout', 'offers',
    'price', 'searchPlaceholder', 'all', 'sessions', 'homeTab', 'communityTab', 'offersFilter',
    'shopFilter', 'bookBtn', 'viewVisitor', 'faq', 'selectOffer', 'bookNow', 'home', 'shop',
    'seeProfile', 'discoverCta'];
  // Mots qui s'écrivent PAREIL en français, en anglais, en allemand… : les compter comme « non
  // traduits » ferait échouer le test pour une raison qui n'en est pas une.
  const IDENTIQUES_PAR_NATURE = new Set(['v_photo', 'v_zoom', 'vm_minutes', 'vm_options', 'vm_association',
    'total', 'code', 'reservationCode', 'date', 'liveNav', 'audioShop', 'email', 'sessions', 'shopFilter',
    'shop', 'v_impressum', 'vm_tva', 'all']);


  // Deux sources de vérité, deux façons de mesurer :
  //  - la table VISITEUR : l'entrée PRÉSENTE dans la table prouve que la langue a été traitée
  //    (un mot identique au français — « WhatsApp », « QR » — est alors volontaire) ;
  //  - le dictionnaire d'App.js (VISITEUR_APP + vocabulaire de base) : on compare au français.
  const CLES_TABLE = Object.keys(VISITEUR);
  const CLES_DICT = [...new Set([...Object.keys(VISITEUR_APP), ...BASE])].filter((k) => !IDENTIQUES_PAR_NATURE.has(k));
  const part = (lang) => {
    const d = fusion[lang] || {};
    const fr = fusion.fr;
    const okTable = CLES_TABLE.filter((k) => typeof VISITEUR[k][lang] === 'string' && VISITEUR[k][lang].trim());
    const okDict = CLES_DICT.filter((k) => typeof d[k] === 'string' && d[k].trim() && (lang === 'fr' || d[k] !== fr[k]));
    const total = CLES_TABLE.length + CLES_DICT.length;
    const manquantes = [
      ...CLES_TABLE.filter((k) => !okTable.includes(k)),
      ...CLES_DICT.filter((k) => !okDict.includes(k)),
    ];
    return { ok: okTable.length + okDict.length, total, manquantes };
  };

  it('le périmètre est conséquent', () => {
    expect(CLES_TABLE.length + CLES_DICT.length).toBeGreaterThan(350);
  });

  it.each([...LANGUES_COMPLETES, ...LANGUES_A_RELIRE])('⚠️ %s : 100 % du périmètre visiteur est traduit', (l) => {
    // Toute NOUVELLE clé visiteur doit être livrée avec ses quatre traductions, sinon
    // cette langue afficherait du français en se disant traduite.
    expect(part(l).manquantes).toEqual([]);
  });

  it.each(LANGUES_PARTIELLES)('%s : DÉCLARÉE partielle, et réellement partielle (< 10 % du périmètre)', (l) => {
    const c = part(l);
    expect(c.ok / c.total).toBeLessThan(0.1);
    expect(TRANSLATE_LANGS.find((x) => x.code === l).status).toBe('partial');
  });

  it('couverture() donne le chiffre qu\'on doit annoncer — jamais « disponible » à la place d\'un pourcentage', () => {
    const c = couverture('en');
    expect(c).toEqual(expect.objectContaining({ langue: 'en' }));
    expect(c.pourcent).toBeGreaterThan(0);
    expect(couverture('fr').pourcent).toBe(100);
  });

  if (process.env.I18N_RAPPORT) {
    it('RAPPORT (I18N_RAPPORT=1) — couverture du périmètre visiteur par langue', () => {
      const lignes = TRANSLATE_LANGS.map((l) => {
        const c = part(l.code);
        return `${l.code.padEnd(4)} ${l.status.padEnd(9)} ${String(c.ok).padStart(3)}/${c.total}  ${(100 * c.ok / c.total).toFixed(1).padStart(5)} %`;
      });
      // eslint-disable-next-line no-console
      console.log('\nCOUVERTURE DU PÉRIMÈTRE VISITEUR\n' + lignes.join('\n'));
    });
  }
});

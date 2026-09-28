/**
 * V554 — disposition libre du Hero : fonctions pures de utils/heroLayout.js.
 */
import {
  HERO_ELEMENTS,
  HERO_SEUIL_MOBILE,
  HERO_DEFAUTS,
  HERO_ZONES_SURES,
  HERO_TEXTES_DEFAUT,
  appareilPour,
  normaliserLayout,
  dispositionPour,
  elementEffectif,
  borner,
  pxVersNormalise,
  normaliseVersPx,
  deplacer,
  changerTaille,
  changerAlignement,
  reinitialiserElement,
  reinitialiserAppareil,
  layoutsEgaux,
  texteHero,
  fusionnerConceptVitrine,
} from '../heroLayout';

const gele = (o) => {
  if (o && typeof o === 'object') { Object.values(o).forEach(gele); Object.freeze(o); }
  return o;
};
const el = (x, y, extra = {}) => ({ x, y, size: 1, align: 'center', ...extra });
const cta = (x, y, size = 1) => ({ x, y, size });
const LAYOUT = () => gele({
  v: 1,
  desktop: { title: el(0.3, 0.2), subtitle: el(0.3, 0.4, { align: 'left' }), cta: cta(0.3, 0.7) },
  mobile: { title: el(0.5, 0.3, { size: 1.2 }), subtitle: null, cta: cta(0.5, 0.6) },
});

describe('constantes', () => {
  test('elements et seuil figés par le contrat', () => {
    expect(HERO_ELEMENTS).toEqual(['title', 'subtitle', 'cta']);
    expect(HERO_SEUIL_MOBILE).toBe(1024);
  });
  test('zones sûres = paddings historiques du mode flux (origin/main)', () => {
    expect(HERO_ZONES_SURES.mobile).toEqual({ haut: 44, bas: 104, cote: 12 });
    expect(HERO_ZONES_SURES.desktop).toEqual({ haut: 44, bas: 56, cote: 12 });
  });
  test('défauts : dans [0,1], size 1, align center (sauf CTA)', () => {
    ['desktop', 'mobile'].forEach((app) => HERO_ELEMENTS.forEach((e) => {
      const d = HERO_DEFAUTS[app][e];
      expect(d.x).toBeGreaterThanOrEqual(0); expect(d.x).toBeLessThanOrEqual(1);
      expect(d.y).toBeGreaterThanOrEqual(0); expect(d.y).toBeLessThanOrEqual(1);
      expect(d.size).toBe(1);
      if (e === 'cta') expect(d.align).toBeUndefined(); else expect(d.align).toBe('center');
    }));
    // ordre vertical conservé : titre au-dessus du sous-titre au-dessus du CTA
    ['desktop', 'mobile'].forEach((app) => {
      expect(HERO_DEFAUTS[app].title.y).toBeLessThan(HERO_DEFAUTS[app].subtitle.y);
      expect(HERO_DEFAUTS[app].subtitle.y).toBeLessThan(HERO_DEFAUTS[app].cta.y);
    });
  });
});

describe('appareilPour — largeur de la BOITE', () => {
  test.each([[0, 'mobile'], [360, 'mobile'], [1023, 'mobile'], [1023.9, 'mobile'], [1024, 'desktop'], [1440, 'desktop']])(
    '%p px -> %s', (l, a) => expect(appareilPour(l)).toBe(a));
  test('entrées invalides -> mobile', () => {
    [undefined, null, NaN, '1440', Infinity].forEach((v) => expect(appareilPour(v)).toBe('mobile'));
  });
});

describe('normaliserLayout — mêmes règles que le serveur', () => {
  test('valeur non-objet -> null', () => {
    [null, undefined, 3, 'x', [], true].forEach((v) => expect(normaliserLayout(v)).toBeNull());
  });
  test('les deux appareils null -> null (remise à zéro complète)', () => {
    expect(normaliserLayout({ v: 1, desktop: null, mobile: null })).toBeNull();
    expect(normaliserLayout({})).toBeNull();
  });
  test('bornes x/y [0,1], size [0.6,1.8], align par défaut center', () => {
    const n = normaliserLayout({ desktop: { title: { x: -3, y: 9, size: 99, align: 'diagonal' }, cta: { x: 0.5, y: 0.5, size: 0.1, align: 'left' } } });
    expect(n.desktop.title).toEqual({ x: 0, y: 1, size: 1.8, align: 'center' });
    expect(n.desktop.cta).toEqual({ x: 0.5, y: 0.5, size: 0.6 }); // pas d'align sur le CTA
    expect(n.desktop.subtitle).toBeNull();
    expect(n.mobile).toBeNull();
    expect(n.v).toBe(1);
  });
  test('types invalides retirés : bool, chaîne, NaN, Infinity', () => {
    const n = normaliserLayout({ mobile: {
      title: { x: true, y: 0.5 },
      subtitle: { x: '0.5', y: 0.5 },
      cta: { x: NaN, y: 0.5 },
    }, desktop: { title: { x: 0.2, y: Infinity }, subtitle: { x: 0.1, y: 0.2, size: '2', align: 7 } } });
    expect(n.mobile).toBeNull(); // aucun élément valide
    expect(n.desktop.title).toBeNull();
    expect(n.desktop.subtitle).toEqual({ x: 0.1, y: 0.2, size: 1, align: 'center' });
  });
  test('clés hors schéma retirées (taille bornée)', () => {
    const n = normaliserLayout({ v: 42, pirate: 'x'.repeat(10000), desktop: { title: { x: 0.1, y: 0.1, html: '<script>' }, autre: {} } });
    expect(n).toEqual({ v: 1, desktop: { title: { x: 0.1, y: 0.1, size: 1, align: 'center' }, subtitle: null, cta: null }, mobile: null });
  });
  test('idempotente', () => {
    const n = normaliserLayout(LAYOUT());
    expect(normaliserLayout(n)).toEqual(n);
  });
});

describe('dispositionPour / elementEffectif — fallback sans layout', () => {
  test('sans layout -> null (mode flux) sur les deux appareils', () => {
    [null, undefined, {}, { v: 1, desktop: null, mobile: null }].forEach((l) => {
      expect(dispositionPour(l, 'desktop')).toBeNull();
      expect(dispositionPour(l, 'mobile')).toBeNull();
    });
  });
  test('desktop et mobile indépendants', () => {
    const l = { v: 1, desktop: { title: el(0.1, 0.2) }, mobile: null };
    expect(dispositionPour(l, 'desktop')).not.toBeNull();
    expect(dispositionPour(l, 'mobile')).toBeNull();
  });
  test('élément null dans une disposition existante -> défaut', () => {
    const l = LAYOUT();
    expect(elementEffectif(l, 'mobile', 'subtitle')).toEqual({ ...HERO_DEFAUTS.mobile.subtitle });
    expect(elementEffectif(l, 'mobile', 'title')).toEqual({ x: 0.5, y: 0.3, size: 1.2, align: 'center' });
    expect(elementEffectif(l, 'desktop', 'cta')).toEqual({ x: 0.3, y: 0.7, size: 1, align: 'center' });
    expect(elementEffectif(null, 'desktop', 'title')).toEqual({ ...HERO_DEFAUTS.desktop.title });
  });
});

describe('conversions normalisé <-> px', () => {
  test('aller-retour', () => {
    const px = normaliseVersPx({ x: 0.25, y: 0.75 }, 1440, 387);
    expect(px).toEqual({ x: 360, y: 290.25 });
    expect(pxVersNormalise(px, 1440, 387)).toEqual({ x: 0.25, y: 0.75 });
  });
  test('boîte de taille nulle : pas de division par zéro', () => {
    expect(pxVersNormalise({ x: 10, y: 10 }, 0, 0)).toEqual({ x: 0.5, y: 0.5 });
  });
});

describe('borner — tout l\'élément reste dans la zone sûre', () => {
  const L = 390; const H = 473;
  const z = HERO_ZONES_SURES.mobile;
  const dedans = (p, w, h, app = 'mobile', LL = L, HH = H) => {
    const zz = HERO_ZONES_SURES[app];
    const c = normaliseVersPx(p, LL, HH);
    expect(c.x - w / 2).toBeGreaterThanOrEqual(zz.cote - 1e-9);
    expect(c.x + w / 2).toBeLessThanOrEqual(LL - zz.cote + 1e-9);
    expect(c.y - h / 2).toBeGreaterThanOrEqual(zz.haut - 1e-9);
    expect(c.y + h / 2).toBeLessThanOrEqual(HH - zz.bas + 1e-9);
  };
  test('au centre : inchangé', () => {
    expect(borner({ x: 0.5, y: 0.5 }, 100, 40, L, H, 'mobile')).toEqual({ x: 0.5, y: 0.5 });
  });
  test.each([[0, 0], [1, 0], [0, 1], [1, 1], [-2, 3], [5, -5]])('coin / hors cadre (%p, %p)', (x, y) => {
    const p = borner({ x, y }, 200, 60, L, H, 'mobile');
    dedans(p, 200, 60);
  });
  test('coin haut-gauche : collé exactement aux bords de la zone', () => {
    const p = normaliseVersPx(borner({ x: 0, y: 0 }, 200, 60, L, H, 'mobile'), L, H);
    expect(p.x).toBeCloseTo(z.cote + 100, 6);
    expect(p.y).toBeCloseTo(z.haut + 30, 6);
  });
  test('élément plus grand que la zone : centré dans la zone', () => {
    const p = normaliseVersPx(borner({ x: 0, y: 1 }, 1000, 1000, L, H, 'mobile'), L, H);
    expect(p.x).toBeCloseTo(L / 2, 6);
    expect(p.y).toBeCloseTo(z.haut + (H - z.haut - z.bas) / 2, 6);
  });
  test('desktop utilise ses propres zones', () => {
    const p = normaliseVersPx(borner({ x: 0.5, y: 1 }, 100, 40, 1440, 387, 'desktop'), 1440, 387);
    expect(p.y).toBeCloseTo(387 - HERO_ZONES_SURES.desktop.bas - 20, 6);
    const q = normaliseVersPx(borner({ x: 0.5, y: 0 }, 100, 40, 1440, 387, 'desktop'), 1440, 387);
    expect(q.y).toBeCloseTo(HERO_ZONES_SURES.desktop.haut + 20, 6);
    dedans(borner({ x: 1, y: 1 }, 300, 50, 1440, 387, 'desktop'), 300, 50, 'desktop', 1440, 387);
  });
  test('boîte non mesurée : position rendue telle quelle', () => {
    expect(borner({ x: 0.9, y: 0.1 }, 10, 10, 0, 0, 'mobile')).toEqual({ x: 0.9, y: 0.1 });
  });
});

describe('deplacer', () => {
  const depart = { title: { x: 0.5, y: 0.38 }, subtitle: { x: 0.5, y: 0.47 }, cta: { x: 0.5, y: 0.58 } };
  test('depuis le mode flux : les éléments non déplacés restent à leur position mesurée (aucun saut)', () => {
    const l = deplacer(null, 'mobile', 'title', { x: 0.4, y: 0.3 }, depart);
    expect(l.v).toBe(1);
    expect(l.desktop).toBeNull();
    expect(l.mobile.title).toEqual({ x: 0.4, y: 0.3, size: 1, align: 'center' });
    expect(l.mobile.subtitle).toEqual({ x: 0.5, y: 0.47, size: 1, align: 'center' });
    expect(l.mobile.cta).toEqual({ x: 0.5, y: 0.58, size: 1 });
  });
  test('déplacement nul depuis le flux = figer les positions mesurées', () => {
    const l = deplacer(null, 'desktop', 'cta', depart.cta, depart);
    HERO_ELEMENTS.forEach((e) => {
      expect(l.desktop[e].x).toBe(depart[e].x);
      expect(l.desktop[e].y).toBe(depart[e].y);
    });
  });
  test('sans positionsDepart : défauts', () => {
    const l = deplacer(null, 'desktop', 'title', { x: 0.1, y: 0.2 });
    expect(l.desktop.cta).toEqual({ ...HERO_DEFAUTS.desktop.cta });
  });
  test('bornage [0,1] et arrondi', () => {
    const l = deplacer(LAYOUT(), 'desktop', 'title', { x: 1.7, y: 0.123456789 });
    expect(l.desktop.title.x).toBe(1);
    expect(l.desktop.title.y).toBe(0.1235);
  });
  test('l\'autre appareil et les autres éléments intacts ; immuable', () => {
    const avant = LAYOUT();
    const l = deplacer(avant, 'desktop', 'cta', { x: 0.8, y: 0.8 });
    expect(l).not.toBe(avant);
    expect(l.mobile).toEqual(avant.mobile);
    expect(l.desktop.title).toEqual(avant.desktop.title);
    expect(l.desktop.subtitle).toEqual(avant.desktop.subtitle);
    expect(avant.desktop.cta).toEqual(cta(0.3, 0.7)); // entrée non modifiée
  });
  test('même position -> même référence (pas de setState identique)', () => {
    const avant = LAYOUT();
    expect(deplacer(avant, 'desktop', 'cta', { x: 0.3, y: 0.7 })).toBe(avant);
  });
  test('entrées invalides -> layout inchangé', () => {
    const avant = LAYOUT();
    expect(deplacer(avant, 'desktop', 'cta', { x: 'a', y: 1 })).toBe(avant);
    expect(deplacer(avant, 'desktop', 'logo', { x: 0.1, y: 1 })).toBe(avant);
    expect(deplacer(avant, 'desktop', 'cta', null)).toBe(avant);
  });
  test('élément null d\'une disposition existante : part de son défaut', () => {
    const l = deplacer(LAYOUT(), 'mobile', 'subtitle', { x: 0.2, y: 0.5 });
    expect(l.mobile.subtitle).toEqual({ x: 0.2, y: 0.5, size: 1, align: 'center' });
  });
});

describe('changerTaille / changerAlignement', () => {
  test('taille bornée [0.6, 1.8]', () => {
    let l = LAYOUT();
    for (let i = 0; i < 20; i++) l = changerTaille(l, 'desktop', 'title', 0.1);
    expect(l.desktop.title.size).toBe(1.8);
    for (let i = 0; i < 40; i++) l = changerTaille(l, 'desktop', 'title', -0.1);
    expect(l.desktop.title.size).toBe(0.6);
  });
  test('pas d\'erreur d\'arrondi flottant', () => {
    const l = changerTaille(changerTaille(LAYOUT(), 'desktop', 'cta', 0.1), 'desktop', 'cta', 0.2);
    expect(l.desktop.cta.size).toBe(1.3);
  });
  test('taille depuis le mode flux : crée la disposition depuis positionsDepart', () => {
    const l = changerTaille(null, 'mobile', 'cta', 0.2, { title: { x: 0.5, y: 0.4 }, subtitle: { x: 0.5, y: 0.5 }, cta: { x: 0.5, y: 0.6 } });
    expect(l.mobile.cta).toEqual({ x: 0.5, y: 0.6, size: 1.2 });
    expect(l.desktop).toBeNull();
  });
  test('alignement : left/center/right seulement, jamais sur le CTA', () => {
    const avant = LAYOUT();
    const l = changerAlignement(avant, 'desktop', 'title', 'right');
    expect(l.desktop.title.align).toBe('right');
    expect(l.desktop.title.x).toBe(0.3);
    expect(changerAlignement(avant, 'desktop', 'title', 'justify')).toBe(avant);
    expect(changerAlignement(avant, 'desktop', 'cta', 'left')).toBe(avant);
    expect(changerAlignement(avant, 'desktop', 'subtitle', 'left')).toBe(avant); // déjà left
  });
});

describe('réinitialisations', () => {
  test('élément : revient au défaut, le reste intact', () => {
    const avant = LAYOUT();
    const l = reinitialiserElement(avant, 'desktop', 'title');
    expect(l.desktop.title).toBeNull();
    expect(l.desktop.subtitle).toEqual(avant.desktop.subtitle);
    expect(l.desktop.cta).toEqual(avant.desktop.cta);
    expect(l.mobile).toEqual(avant.mobile);
    expect(elementEffectif(l, 'desktop', 'title')).toEqual({ ...HERO_DEFAUTS.desktop.title });
  });
  test('dernier élément réinitialisé -> disposition null (mode flux, comme le serveur)', () => {
    let l = reinitialiserElement(LAYOUT(), 'mobile', 'title');
    l = reinitialiserElement(l, 'mobile', 'cta');
    expect(l.mobile).toBeNull();
    expect(l.desktop).toEqual(LAYOUT().desktop);
  });
  test('élément déjà au défaut / pas de layout : même référence', () => {
    const avant = LAYOUT();
    expect(reinitialiserElement(avant, 'mobile', 'subtitle')).toBe(avant);
    expect(reinitialiserElement(null, 'mobile', 'title')).toBeNull();
  });
  test('appareil : null pour lui, l\'autre intact, textes jamais concernés', () => {
    const avant = LAYOUT();
    const l = reinitialiserAppareil(avant, 'mobile');
    expect(l).toEqual({ v: 1, desktop: avant.desktop, mobile: null });
    expect(avant.mobile).not.toBeNull();
    expect(Object.keys(l).sort()).toEqual(['desktop', 'mobile', 'v']);
  });
  test('appareil sans layout : charge utile explicite pour le PUT', () => {
    expect(reinitialiserAppareil(null, 'desktop')).toEqual({ v: 1, desktop: null, mobile: null });
  });
});

describe('layoutsEgaux', () => {
  test('null ≡ {v:1, desktop:null, mobile:null}', () => {
    expect(layoutsEgaux(null, { v: 1, desktop: null, mobile: null })).toBe(true);
    expect(layoutsEgaux(undefined, null)).toBe(true);
  });
  test('égalité structurelle, pas de référence', () => {
    expect(layoutsEgaux(LAYOUT(), JSON.parse(JSON.stringify(LAYOUT())))).toBe(true);
  });
  test('défauts implicites comparés après normalisation', () => {
    expect(layoutsEgaux({ desktop: { title: { x: 0.1, y: 0.1 } } }, { v: 1, desktop: { title: el(0.1, 0.1), subtitle: null, cta: null }, mobile: null })).toBe(true);
  });
  test('toute différence compte', () => {
    const a = LAYOUT();
    expect(layoutsEgaux(a, deplacer(a, 'desktop', 'title', { x: 0.31, y: 0.2 }))).toBe(false);
    expect(layoutsEgaux(a, changerTaille(a, 'mobile', 'cta', 0.1))).toBe(false);
    expect(layoutsEgaux(a, changerAlignement(a, 'desktop', 'title', 'left'))).toBe(false);
    expect(layoutsEgaux(a, reinitialiserAppareil(a, 'desktop'))).toBe(false);
    expect(layoutsEgaux(a, null)).toBe(false);
  });
});

describe('textes du Hero (V547, inchangés)', () => {
  test('défauts caractère pour caractère', () => {
    expect(HERO_TEXTES_DEFAUT.title).toBe('Danse. Transpire. Lâche prise.');
    expect(HERO_TEXTES_DEFAUT.cta).toBe('Réserver mon 1er cours gratuit');
  });
  test('vide ou espaces -> défaut', () => {
    expect(texteHero('  ', 'D')).toBe('D');
    expect(texteHero(undefined, 'D')).toBe('D');
    expect(texteHero(12, 'D')).toBe('D');
    expect(texteHero('Salut', 'D')).toBe('Salut');
  });
});

describe('fusionnerConceptVitrine — la disposition du super-admin ne fuit pas', () => {
  const accueil = gele({ appName: 'Afroboost', heroTitle: 'T', heroLayout: LAYOUT() });
  test('partenaire sans heroLayout -> null (jamais celui de l\'accueil)', () => {
    const c = fusionnerConceptVitrine(accueil, { appName: 'Partenaire' });
    expect(c.heroLayout).toBeNull();
    expect(c.appName).toBe('Partenaire');
    expect(c.heroTitle).toBe('T'); // comportement historique des autres champs conservé
  });
  test('partenaire avec heroLayout null -> null', () => {
    expect(fusionnerConceptVitrine(accueil, { heroLayout: null }).heroLayout).toBeNull();
  });
  test('partenaire avec sa disposition -> la sienne', () => {
    const sienne = { v: 1, desktop: null, mobile: { title: el(0.2, 0.4) } };
    expect(fusionnerConceptVitrine(accueil, { heroLayout: sienne }).heroLayout).toBe(sienne);
  });
  test('entrées vides tolérées', () => {
    expect(fusionnerConceptVitrine(undefined, undefined)).toEqual({ heroLayout: null });
  });
});

/** FORMAT VIDEO — détection, normalisation, styles fidèles au ratio. */
import { ratioDepuisDimensions, normaliserRatio, ratioValide, aspectCss, stylesLecteur, estPortrait, libelleDetection, RATIOS } from '../videoRatio';

describe('détection depuis les dimensions réelles', () => {
  test('1080 × 1920 → 9:16 ; 1920 × 1080 → 16:9 ; 1080 × 1080 → 1:1', () => {
    expect(ratioDepuisDimensions(1080, 1920)).toBe('9:16');
    expect(ratioDepuisDimensions(1920, 1080)).toBe('16:9');
    expect(ratioDepuisDimensions(1080, 1080)).toBe('1:1');
  });
  test('tolérance : 720 × 1280, 1088 × 1920, 1280 × 720, 1000 × 1040', () => {
    expect(ratioDepuisDimensions(720, 1280)).toBe('9:16');
    expect(ratioDepuisDimensions(1088, 1920)).toBe('9:16');
    expect(ratioDepuisDimensions(1280, 720)).toBe('16:9');
    expect(ratioDepuisDimensions(1000, 1040)).toBe('1:1');
  });
  test('4:3 ou 3:2 restent « auto » (on n’invente pas un cadre) ; dimensions inconnues → auto', () => {
    expect(ratioDepuisDimensions(1440, 1080)).toBe('auto');
    expect(ratioDepuisDimensions(0, 0)).toBe('auto');
    expect(ratioDepuisDimensions(undefined, null)).toBe('auto');
  });
});

describe('normalisation', () => {
  test('les 4 valeurs sont valides, tout le reste devient auto', () => {
    expect(RATIOS.map((r) => r.valeur)).toEqual(['auto', '9:16', '16:9', '1:1']);
    expect(ratioValide('9:16')).toBe(true);
    expect(ratioValide('4:3')).toBe(false);
    expect(normaliserRatio('4:3')).toBe('auto');
    expect(normaliserRatio(undefined)).toBe('auto');
    expect(aspectCss('9:16')).toBe('9 / 16');
    expect(aspectCss('auto')).toBe('');
  });
});

describe('styles du lecteur : jamais étiré, jamais rogné', () => {
  test('toujours object-fit contain, fond derrière', () => {
    ['auto', '9:16', '16:9', '1:1'].forEach((r) => {
      const st = stylesLecteur(r, { hauteurMax: '60vh' });
      expect(st.video.objectFit).toBe('contain');
      expect(st.conteneur.background).toMatch(/--video-bg/);
      expect(st.video.maxHeight).toBe('60vh');
    });
  });
  test('9:16 = colonne centrée bornée en hauteur ; 16:9 = pleine largeur ; 1:1 = carré', () => {
    expect(stylesLecteur('9:16', { hauteurMax: '60vh' }).video).toMatchObject({ height: '60vh', width: 'auto', aspectRatio: '9 / 16' });
    expect(stylesLecteur('16:9').video).toMatchObject({ width: '100%', aspectRatio: '16 / 9' });
    expect(stylesLecteur('1:1').video.aspectRatio).toBe('1 / 1');
    expect(stylesLecteur('auto').video.aspectRatio).toBeUndefined();
    expect(stylesLecteur('9:16').conteneur.justifyContent).toBe('center');
  });
});

describe('portrait', () => {
  test('9:16 stocké = portrait ; 16:9 / 1:1 = non ; auto = selon les dimensions mesurées', () => {
    expect(estPortrait('9:16')).toBe(true);
    expect(estPortrait('16:9', 100, 200)).toBe(false);
    expect(estPortrait('1:1', 100, 200)).toBe(false);
    expect(estPortrait('auto', 1080, 1920)).toBe(true);
    expect(estPortrait('auto', 1920, 1080)).toBe(false);
    expect(estPortrait('auto')).toBe(false);
  });
  test('libellé de détection', () => {
    expect(libelleDetection(1080, 1920)).toBe('1080 × 1920 → 9:16');
    expect(libelleDetection(1440, 1080)).toBe('1440 × 1080 → format libre');
    expect(libelleDetection(0, 0)).toBe('');
  });
});

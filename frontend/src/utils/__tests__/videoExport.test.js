/**
 * V596 — export vidéo navigateur : la partie PURE (cadre, dimensions, validation).
 * Le moteur (Mediabunny) n'est jamais chargé ici : il ne l'est qu'à l'export réel.
 */
import fs from 'fs';
import path from 'path';
import {
  calculerCadrage, validerFichierVideo, validerMetadonnees, nomExport, debitVideo,
  exportSupporteIci, FORMATS_EXPORT,
} from '../videoExport';

describe('calculerCadrage — vrai recadrage, sans bandes, sans agrandissement', () => {
  test('16:9 1920×1080 → 9:16 : cadre vertical 608×1080, centré par défaut', () => {
    const r = calculerCadrage(1920, 1080, '9:16');
    expect(r.axe).toBe('x');
    expect(r.cadre).toEqual({ gauche: 656, haut: 0, largeur: 608, hauteur: 1080 });
    expect(r.sortie).toEqual({ largeur: 608, hauteur: 1080 });   // jamais agrandi en 1080×1920
  });
  test('9:16 : gauche / droite collent aux bords', () => {
    expect(calculerCadrage(1920, 1080, '9:16', 0).cadre.gauche).toBe(0);
    const d = calculerCadrage(1920, 1080, '9:16', 1).cadre;
    expect(d.gauche + d.largeur).toBe(1920);
  });
  test('16:9 → 1:1 : 1080×1080', () => {
    const r = calculerCadrage(1920, 1080, '1:1');
    expect(r.cadre.largeur).toBe(1080);
    expect(r.sortie).toEqual({ largeur: 1080, hauteur: 1080 });
  });
  test('16:9 → 16:9 : aucun cadre à déplacer, plein format', () => {
    const r = calculerCadrage(1920, 1080, '16:9');
    expect(r.axe).toBe(null);
    expect(r.sortie).toEqual({ largeur: 1920, hauteur: 1080 });
  });
  test('vertical 1080×1920 → 16:9 : coupe en HAUT / BAS', () => {
    const r = calculerCadrage(1080, 1920, '16:9', 0);
    expect(r.axe).toBe('y');
    expect(r.cadre.haut).toBe(0);
    expect(r.cadre.largeur).toBe(1080);
    expect(r.cadre.hauteur).toBe(608);
    const bas = calculerCadrage(1080, 1920, '16:9', 1).cadre;
    expect(bas.haut + bas.hauteur).toBe(1920);
  });
  test('source 4K : sortie plafonnée au maximum du format', () => {
    expect(calculerCadrage(3840, 2160, '16:9').sortie).toEqual({ largeur: 1920, hauteur: 1080 });
    expect(calculerCadrage(2160, 3840, '9:16').sortie).toEqual({ largeur: 1080, hauteur: 1920 });
  });
  test('dimensions toujours paires (H.264)', () => {
    const r = calculerCadrage(1279, 721, '9:16', 0.37);
    [r.cadre.largeur, r.cadre.hauteur, r.sortie.largeur, r.sortie.hauteur].forEach((n) => expect(n % 2).toBe(0));
    expect(r.cadre.gauche + r.cadre.largeur).toBeLessThanOrEqual(1279);
  });
  test('auto : pas de recadrage', () => {
    const r = calculerCadrage(1920, 1080, 'auto');
    expect(r.cadre).toEqual({ gauche: 0, haut: 0, largeur: 1920, hauteur: 1080 });
  });
  test('position hors limites bornée', () => {
    expect(calculerCadrage(1920, 1080, '9:16', 7).cadre.gauche).toBe(1312);
    expect(calculerCadrage(1920, 1080, '9:16', -3).cadre.gauche).toBe(0);
  });
});

describe('validation avant traitement', () => {
  const f = (name, type, size) => ({ name, type, size });
  test('MP4 22 Mo accepté', () => expect(validerFichierVideo(f('festival.mp4', 'video/mp4', 22538851))).toBe(''));
  test('extension refusée', () => expect(validerFichierVideo(f('x.exe', 'video/mp4', 10))).toMatch(/Extension/));
  test('type refusé', () => expect(validerFichierVideo(f('x.mp4', 'text/html', 10))).toMatch(/Type/));
  test('trop lourd', () => expect(validerFichierVideo(f('x.mp4', 'video/mp4', 101 * 1024 * 1024))).toMatch(/trop lourd/));
  test('trop long', () => expect(validerMetadonnees({ duree: 601, largeur: 1, hauteur: 1 })).toMatch(/trop longue/));
  test('durée illisible', () => expect(validerMetadonnees({ duree: NaN, largeur: 1, hauteur: 1 })).toMatch(/illisible/));
});

test('nom du fichier exporté', () => {
  expect(nomExport('AFROBOOST_6_FESTIVAL_16x9_AVEC-COACH.mp4', '9:16')).toBe('AFROBOOST_6_FESTIVAL_16x9_AVEC-COACH_9x16.mp4');
  expect(nomExport('../../etc/pass wd.mov', '1:1')).toBe('etc_pass_wd_1x1.mp4');
});

test('débit raisonnable (≈ 4 Mbit/s en 1080p, borné)', () => {
  expect(debitVideo(1920, 1080)).toBeGreaterThan(3500000);
  expect(debitVideo(1920, 1080)).toBeLessThanOrEqual(5000000);
  expect(debitVideo(320, 180)).toBe(1500000);
});

test('téléphone : export refusé avec le message demandé', () => {
  const r = exportSupporteIci({ navigator: { userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)' }, VideoEncoder: function E() {}, VideoDecoder: function D() {} });
  expect(r.ok).toBe(false);
  expect(r.raison).toBe('Export vidéo recommandé sur ordinateur.');
});
test('ordinateur avec WebCodecs : export permis', () => {
  const r = exportSupporteIci({ navigator: { userAgent: 'Mozilla/5.0 (Macintosh)' }, matchMedia: () => ({ matches: false }), innerWidth: 1440, VideoEncoder: function E() {}, VideoDecoder: function D() {} });
  expect(r.ok).toBe(true);
});

test('le moteur n’est chargé qu’à la demande (import() dynamique, jamais en tête de fichier)', () => {
  const src = fs.readFileSync(path.join(__dirname, '..', 'videoExport.js'), 'utf8');
  expect(src).not.toMatch(/^import .*mediabunny/m);
  expect(src).toMatch(/await import\('mediabunny'\)/);
  const racine = path.join(__dirname, '..', '..');
  const fautifs = [];
  const parcourir = (d) => fs.readdirSync(d, { withFileTypes: true }).forEach((e) => {
    const p = path.join(d, e.name);
    if (e.isDirectory()) { if (e.name !== '__tests__' && e.name !== 'node_modules') parcourir(p); return; }
    if (!/\.js$/.test(e.name) || p.endsWith('videoExport.js')) return;
    const t = fs.readFileSync(p, 'utf8');
    if (/from ['"]mediabunny|from ['"]@mediabunny/.test(t)) fautifs.push(p);
  });
  parcourir(racine);
  expect(fautifs).toEqual([]);
});

test('l’éditeur Prospection est chargé avec lazy(), jamais importé statiquement', () => {
  const src = fs.readFileSync(path.join(__dirname, '..', '..', 'components', 'coach', 'prospection', 'ProspectionMedias.js'), 'utf8');
  expect(src).toMatch(/lazy\(\(\) => import\('\.\/ProspectionVideoEditeur'\)\)/);
  expect(src).not.toMatch(/^import .*ProspectionVideoEditeur/m);
});

test('4 formats proposés : Auto, 16:9, 9:16, 1:1', () => {
  expect(FORMATS_EXPORT.map((f) => f.ratio)).toEqual(['auto', '16:9', '9:16', '1:1']);
});

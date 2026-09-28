/**
 * V554 — editeur visuel du Hero : la logique pure (echelle, pointeur,
 * fleches, taille, media d'apercu, decision d'ecriture au relachement).
 */
import {
  APERCU_DIMENSIONS,
  aBougeAssez,
  decaler,
  directionDeTouche,
  echelleApercu,
  ecartSaisie,
  layoutAEcrire,
  layoutPourEnvoi,
  libelleStatut,
  mediaApercu,
  pasFleche,
  peutAgrandir,
  peutReduire,
  pointeurVersCentre,
  pourcentageTaille,
  tailleCadre,
} from '../heroEditeur';
import { deplacer, dispositionPour, HERO_ZONES_SURES } from '../heroLayout';

describe('echelle de l\'apercu', () => {
  test('desktop 1440 dans 720 px -> 0,5 ; hauteur = 387 x 0,5', () => {
    expect(echelleApercu(720, 'desktop')).toBe(0.5);
    expect(tailleCadre(720, 'desktop')).toEqual({ echelle: 0.5, largeur: 720, hauteur: 193.5 });
  });
  test('jamais agrandie au-dela de 1 ; largeur nulle -> 0', () => {
    expect(echelleApercu(2000, 'desktop')).toBe(1);
    expect(echelleApercu(600, 'mobile')).toBe(1);
    expect(echelleApercu(0, 'mobile')).toBe(0);
    expect(echelleApercu(undefined, 'mobile')).toBe(0);
  });
  test('mobile 386 dans 308,8 px -> 0,8', () => {
    expect(echelleApercu(308.8, 'mobile')).toBeCloseTo(0.8, 5);
    expect(APERCU_DIMENSIONS.mobile).toEqual({ largeur: 386, hauteur: 473 });
  });
});

describe('pointeur -> normalise (avec echelle)', () => {
  const rect = { left: 100, top: 50 };
  test('sans ecart : centre = pointeur ramene a la boite native', () => {
    // ecran (100 + 360, 50 + 96.75) a l'echelle 0,5 -> boite (720, 193.5) -> (0.5, 0.5)
    const c = pointeurVersCentre({ x: 460, y: 146.75 }, rect, 0.5, { x: 0, y: 0 }, 1440, 387);
    expect(c.x).toBeCloseTo(0.5, 6);
    expect(c.y).toBeCloseTo(0.5, 6);
  });
  test('l\'ecart memorise a la prise est conserve (aucun saut)', () => {
    const centre = { x: 0.5, y: 0.2 };
    const prise = { x: 480, y: 90 }; // un peu a droite / en dessous du centre
    const ecart = ecartSaisie(prise, rect, 0.5, centre, 1440, 387);
    const memePoint = pointeurVersCentre(prise, rect, 0.5, ecart, 1440, 387);
    expect(memePoint.x).toBeCloseTo(0.5, 6);
    expect(memePoint.y).toBeCloseTo(0.2, 6);
    // 72 px ecran vers la droite = 144 px natifs = 0,1 de 1440
    const apres = pointeurVersCentre({ x: 552, y: 90 }, rect, 0.5, ecart, 1440, 387);
    expect(apres.x).toBeCloseTo(0.6, 6);
  });
  test('seuil de glissement : 2 px = clic, 3 px = glisser', () => {
    expect(aBougeAssez({ x: 0, y: 0 }, { x: 2, y: 0 })).toBe(false);
    expect(aBougeAssez({ x: 0, y: 0 }, { x: 3, y: 0 })).toBe(true);
    expect(aBougeAssez(null, { x: 9, y: 9 })).toBe(false);
  });
});

describe('fleches', () => {
  test('pas 1 %, Maj 5 %', () => {
    expect(pasFleche('haut', false)).toEqual({ dx: 0, dy: -0.01 });
    expect(pasFleche('droite', true)).toEqual({ dx: 0.05, dy: 0 });
    expect(pasFleche('nulle', false)).toEqual({ dx: 0, dy: 0 });
    expect(directionDeTouche('ArrowLeft')).toBe('gauche');
    expect(directionDeTouche('a')).toBe(null);
  });
  test('depuis le mode flux : cree la disposition a partir des positions affichees', () => {
    const pos = { title: { x: 0.5, y: 0.2 }, subtitle: { x: 0.5, y: 0.38 }, cta: { x: 0.5, y: 0.6 } };
    const l = decaler(null, 'desktop', 'title', 'bas', false, pos);
    expect(l.desktop.title.y).toBeCloseTo(0.21, 6);
    expect(l.desktop.cta).toEqual({ x: 0.5, y: 0.6, size: 1 });
    expect(l.mobile).toBe(null);
  });
  test('bornee dans la zone sure quand les dimensions sont connues', () => {
    const pos = { title: { x: 0.5, y: 0.13 }, subtitle: { x: 0.5, y: 0.38 }, cta: { x: 0.5, y: 0.6 } };
    const dims = { largeurEl: 400, hauteurEl: 60, largeurBoite: 1440, hauteurBoite: 387 };
    const l = decaler(null, 'desktop', 'title', 'haut', true, pos, dims);
    const minY = (HERO_ZONES_SURES.desktop.haut + 30) / 387;
    expect(l.desktop.title.y).toBeCloseTo(minY, 3);
  });
  test('sans position connue : layout inchange (meme reference)', () => {
    const l0 = { v: 1, desktop: null, mobile: null };
    expect(decaler(l0, 'desktop', 'title', 'haut', false, null)).toBe(l0);
  });
});

describe('taille', () => {
  test('affichage en % et bornes', () => {
    expect(pourcentageTaille(1)).toBe('100 %');
    expect(pourcentageTaille(1.3)).toBe('130 %');
    expect(pourcentageTaille(undefined)).toBe('100 %');
    expect(peutReduire(0.6)).toBe(false);
    expect(peutReduire(0.7)).toBe(true);
    expect(peutAgrandir(1.8)).toBe(false);
    expect(peutAgrandir(1.7)).toBe(true);
  });
});

describe('ecrire ou non au relachement', () => {
  const pos = { title: { x: 0.5, y: 0.2 }, subtitle: { x: 0.5, y: 0.38 }, cta: { x: 0.5, y: 0.6 } };
  test('simple clic : rien', () => {
    const fin = deplacer(null, 'desktop', 'title', { x: 0.3, y: 0.3 }, pos);
    expect(layoutAEcrire(null, fin, false)).toBe(null);
  });
  test('glisse mais revenu au meme endroit : rien', () => {
    const l0 = deplacer(null, 'desktop', 'title', { x: 0.3, y: 0.3 }, pos);
    const l1 = deplacer(l0, 'desktop', 'title', { x: 0.3, y: 0.3 }, pos);
    expect(layoutAEcrire(l0, l1, true)).toBe(null);
  });
  test('glisse : un OBJET complet, l\'autre appareil conserve', () => {
    const l0 = deplacer(null, 'mobile', 'cta', { x: 0.5, y: 0.7 }, pos);
    const l1 = deplacer(l0, 'desktop', 'title', { x: 0.3, y: 0.3 }, pos);
    const envoi = layoutAEcrire(l0, l1, true);
    expect(envoi.v).toBe(1);
    expect(envoi.desktop.title).toEqual({ x: 0.3, y: 0.3, size: 1, align: 'center' });
    expect(dispositionPour(envoi, 'mobile').cta.y).toBe(0.7);
  });
  test('envoi : jamais null / chaine / liste', () => {
    expect(layoutPourEnvoi(null)).toEqual({ v: 1, desktop: null, mobile: null });
    expect(layoutPourEnvoi('x')).toEqual({ v: 1, desktop: null, mobile: null });
    expect(layoutPourEnvoi([])).toEqual({ v: 1, desktop: null, mobile: null });
  });
});

describe('media de l\'apercu', () => {
  test('premier media VISIBLE', () => {
    const c = { heroVideos: [{ url: 'https://x/a.jpg', is_visible: false }, null, { url: '' }, { url: 'https://x/b.png' }] };
    expect(mediaApercu(c)).toEqual({ type: 'image', url: 'https://x/b.png' });
  });
  test('YouTube -> miniature hqdefault', () => {
    const c = { heroVideos: [{ url: 'https://youtu.be/dQw4w9WgXcQ', type: 'youtube' }] };
    expect(mediaApercu(c)).toEqual({ type: 'image', url: 'https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg' });
  });
  test('video uploadee -> video', () => {
    expect(mediaApercu({ heroVideos: [{ url: '/api/files/abc/video_1.mp4' }] }).type).toBe('video');
    expect(mediaApercu({ heroVideos: [{ url: 'https://res.cloudinary.com/x/video/upload/v1/a.mp4' }] }).type).toBe('video');
  });
  test('repli heroImageUrl, sinon fond noir', () => {
    expect(mediaApercu({ heroVideos: [], heroImageUrl: 'https://x/h.jpg' })).toEqual({ type: 'image', url: 'https://x/h.jpg' });
    expect(mediaApercu({})).toEqual({ type: 'aucun', url: '' });
    expect(mediaApercu(null)).toEqual({ type: 'aucun', url: '' });
    expect(mediaApercu({ heroVideos: [{ url: 'https://vimeo.com/123' }] })).toEqual({ type: 'aucun', url: '' });
  });
});

test('statut discret', () => {
  expect(libelleStatut('saving')).toBe('Enregistrement…');
  expect(libelleStatut('saved')).toBe('Enregistré');
  expect(libelleStatut('error')).toBe("Erreur d'enregistrement");
  expect(libelleStatut(null)).toBe('');
});

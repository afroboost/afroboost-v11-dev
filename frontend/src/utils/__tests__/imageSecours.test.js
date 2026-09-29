// IMG-1 — anti-boucle des images en echec.
// Mesure du banc reel avant correctif : 118 337 requetes en quelques secondes,
// parce qu'un `onError` reassignait une URL qui echouait elle aussi.
import {
  surErreurImage,
  surErreurImageSansSecours,
  imageOuSecours,
  IMAGE_SECOURS_LOCAL,
  IMAGE_FINALE,
} from '../imageSecours';

// Espionne chaque affectation de `src` sur un <img> jsdom.
function imageEspionnee(srcInitial) {
  const img = document.createElement('img');
  if (srcInitial) img.setAttribute('src', srcInitial);
  const affectations = [];
  const desc = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');
  Object.defineProperty(img, 'src', {
    configurable: true,
    get() { return desc.get.call(this); },
    set(v) { affectations.push(v); desc.set.call(this, v); },
  });
  return { img, affectations };
}
const evt = (img) => ({ currentTarget: img, target: img });

describe('imageSecours — secours local', () => {
  test('le secours est servi par le site lui-meme (aucun domaine externe)', () => {
    expect(IMAGE_SECOURS_LOCAL.startsWith('/')).toBe(true);
    expect(IMAGE_SECOURS_LOCAL).not.toMatch(/^\/\//);
    expect(IMAGE_FINALE.startsWith('data:')).toBe(true);
  });

  test('URL vide / absente / non-texte -> secours local direct', () => {
    expect(imageOuSecours('')).toBe(IMAGE_SECOURS_LOCAL);
    expect(imageOuSecours('   ')).toBe(IMAGE_SECOURS_LOCAL);
    expect(imageOuSecours(null)).toBe(IMAGE_SECOURS_LOCAL);
    expect(imageOuSecours(undefined)).toBe(IMAGE_SECOURS_LOCAL);
    expect(imageOuSecours(42)).toBe(IMAGE_SECOURS_LOCAL);
    expect(imageOuSecours(' https://x.test/a.jpg ')).toBe('https://x.test/a.jpg');
  });
});

describe('surErreurImage — bornes', () => {
  test('image valide : aucun appel, aucune affectation', () => {
    const { img, affectations } = imageEspionnee('https://cdn.test/ok.jpg');
    expect(affectations).toHaveLength(0);
    expect(img.getAttribute('data-secours')).toBeNull();
  });

  test('principale en 404 -> exactement 1 bascule vers le secours local', () => {
    const { img, affectations } = imageEspionnee('https://cdn.test/404.jpg');
    surErreurImage(evt(img));
    expect(affectations).toEqual([IMAGE_SECOURS_LOCAL]);
    expect(img.getAttribute('data-secours')).toBe('1');
  });

  test('principale + secours en 404 -> placeholder final, puis plus rien', () => {
    const { img, affectations } = imageEspionnee('https://cdn.test/404.jpg');
    surErreurImage(evt(img));
    surErreurImage(evt(img));
    expect(affectations).toEqual([IMAGE_SECOURS_LOCAL, IMAGE_FINALE]);
    expect(img.getAttribute('data-secours')).toBe('final');
    expect(img.onerror).toBeNull();
    surErreurImage(evt(img));
    surErreurImage(evt(img));
    expect(affectations).toHaveLength(2);
  });

  test('src deja egal au secours (offre sans image) -> final direct, pas de 2e requete du secours', () => {
    const { img, affectations } = imageEspionnee(IMAGE_SECOURS_LOCAL);
    surErreurImage(evt(img));
    expect(affectations).toEqual([IMAGE_FINALE]);
  });

  test('URL externe bloquee (picsum, bloqueur) -> secours local, jamais un domaine externe', () => {
    const { img, affectations } = imageEspionnee('https://picsum.photos/seed/default/400/300');
    surErreurImage(evt(img));
    surErreurImage(evt(img));
    expect(affectations.every((u) => !/^https?:/.test(u))).toBe(true);
  });

  test("10 erreurs d'affilee -> au plus 1 secours + 1 final", () => {
    const { img, affectations } = imageEspionnee('https://cdn.test/404.jpg');
    for (let i = 0; i < 10; i++) surErreurImage(evt(img));
    expect(affectations).toEqual([IMAGE_SECOURS_LOCAL, IMAGE_FINALE]);
  });

  test('secours personnalise (miniature YouTube HQ) -> meme borne', () => {
    const { img, affectations } = imageEspionnee('https://img.youtube.com/vi/x/maxresdefault.jpg');
    for (let i = 0; i < 10; i++) surErreurImage(evt(img), 'https://img.youtube.com/vi/x/hqdefault.jpg');
    expect(affectations).toEqual(['https://img.youtube.com/vi/x/hqdefault.jpg', IMAGE_FINALE]);
  });

  test('evenement vide ou sans cible : ne plante pas', () => {
    expect(() => surErreurImage(null)).not.toThrow();
    expect(() => surErreurImage({})).not.toThrow();
  });
});

describe('surErreurImageSansSecours — logo/apercu sans image de repli', () => {
  test("retire la source une seule fois, garde le texte alt, puis n'agit plus", () => {
    const { img, affectations } = imageEspionnee('https://upload.wikimedia.org/x.svg');
    for (let i = 0; i < 10; i++) surErreurImageSansSecours(evt(img), 'PayPal');
    expect(affectations).toHaveLength(0);          // jamais `src = ''` (qui rebouclait)
    expect(img.hasAttribute('src')).toBe(false);
    expect(img.alt).toBe('PayPal');
    expect(img.getAttribute('data-secours')).toBe('final');
    expect(img.onerror).toBeNull();
  });
});

describe('surErreurImage — cohabitation avec le gestionnaire global V416 (App.js)', () => {
  test("V416 a deja remplace src par un GIF et note l'URL en echec : le secours n'est pas redemande", () => {
    const { img, affectations } = imageEspionnee('data:image/gif;base64,R0lGOD');
    img.setAttribute('data-src-echec', IMAGE_SECOURS_LOCAL);
    surErreurImage(evt(img));
    expect(affectations).toEqual([IMAGE_FINALE]);
  });
});

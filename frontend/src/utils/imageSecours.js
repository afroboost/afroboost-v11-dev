// IMG-1 — secours d'image BORNE, sans boucle.
//
// L'incident : `onError={(e) => { e.target.src = defaultImage; }}` avec
// defaultImage = picsum.photos. Quand picsum est bloque (bloqueur de pub,
// reseau, 404), l'affectation declenche un nouvel `error`, qui reaffecte la
// meme URL, qui echoue... Mesure sur banc reel : 118 337 requetes en quelques
// secondes. (Le gestionnaire global V416 d'App.js ne protegeait pas : il pose
// son marqueur au 1er echec puis se retire, laissant l'onError local boucler.)
//
// La regle, pour TOUTE image :
//   1. image principale ;
//   2. au 1er echec -> secours LOCAL (servi par le site lui-meme) ;
//   3. si le secours echoue aussi -> placeholder final `data:` (ne peut pas
//      echouer, zero requete reseau) ;
//   4. plus AUCUNE affectation de `src` ensuite. Au maximum 2 requetes.
//
// Le marqueur `data-secours` ("1" puis "final") vit sur l'element DOM : c'est
// lui qui borne, pas l'etat React. Quand l'URL principale change (carrousel),
// le composant doit remonter l'<img> (`key={src}`) pour repartir de zero.

// Visuel de marque deja servi par le site (1200x630, fond sombre, logo centre) :
// en object-fit: cover il occupe proprement une carte 400x300.
export const IMAGE_SECOURS_LOCAL = '/og-image.png';

// Placeholder final : SVG vide et transparent (quelques octets, aucune requete).
// C'est le fond CSS pose en meme temps qui donne le rendu (couleurs via var()).
export const IMAGE_FINALE =
  'data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%224%22%20height%3D%223%22%2F%3E';

const FOND_FINAL =
  'linear-gradient(135deg, var(--background-color, #0a0a14) 0%, rgba(var(--primary-rgb, 217, 28, 210), 0.35) 100%)';

// URL exploitable ou secours local : une offre sans image ne part JAMAIS vers
// un domaine externe de remplissage.
export function imageOuSecours(url, secours = IMAGE_SECOURS_LOCAL) {
  if (typeof url === 'string' && url.trim()) return url.trim();
  return secours;
}

function memeUrl(img, url) {
  if (!url) return false;
  // Le gestionnaire global V416 (App.js, phase de capture) passe AVANT nous et
  // remplace deja `src` par un GIF vide : il note l'URL en echec dans
  // `data-src-echec`. On compare aux deux.
  const candidates = [img.getAttribute('src'), img.getAttribute('data-src-echec')];
  if (candidates.indexOf(url) !== -1) return true;
  try {
    const absolue = new URL(url, window.location.href).href;
    return candidates.some((c) => c && new URL(c, window.location.href).href === absolue);
  } catch (e) {
    return false;
  }
}

// Gestionnaire unique a brancher sur `onError` :
//   onError={(e) => surErreurImage(e)}                 // secours local
//   onError={(e) => surErreurImage(e, urlMiniatureHQ)}  // secours dedie
export function surErreurImage(e, secours = IMAGE_SECOURS_LOCAL) {
  const img = e && (e.currentTarget || e.target);
  if (!img || typeof img.getAttribute !== 'function') return;
  const etape = img.getAttribute('data-secours');

  // Deja au placeholder final : on ne touche plus a rien.
  if (etape === 'final') {
    img.onerror = null;
    return;
  }

  // Etape 2 : premier echec, secours pas encore tente (et different de l'URL
  // qui vient d'echouer — sinon ce serait une 2e requete identique).
  if (etape !== '1' && secours && !memeUrl(img, secours)) {
    img.setAttribute('data-secours', '1');
    img.src = secours;
    return;
  }

  // Etape 3 : le secours a echoue (ou etait deja l'URL en echec) -> final.
  img.setAttribute('data-secours', 'final');
  img.onerror = null;
  try {
    img.removeAttribute('srcset');
    img.style.background = FOND_FINAL;
  } catch (err) { /* jamais bloquer le rendu pour une image */ }
  img.src = IMAGE_FINALE;
}

// Variante SANS image de secours : l'element garde sa place et affiche son
// texte `alt` (logos de paiement, apercu d'une URL saisie par le coach).
// Remplace l'ancien `e.target.src = ''` : une source vide redeclenche `error`,
// qui la reaffectait -> boucle d'evenements (sans requete, mais processeur a 100 %).
export function surErreurImageSansSecours(e, alt) {
  const img = e && (e.currentTarget || e.target);
  if (!img || typeof img.getAttribute !== 'function') return;
  img.onerror = null;
  if (img.getAttribute('data-secours') === 'final') return;
  img.setAttribute('data-secours', 'final');
  if (typeof alt === 'string') img.alt = alt;
  // Retirer l'attribut (et non le vider) : aucun nouvel `error`, aucune requete.
  img.removeAttribute('srcset');
  img.removeAttribute('src');
}

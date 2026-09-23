/**
 * V543 — LA BULLE DU CHAT DEVIENT DÉPLAÇABLE.
 *
 * POURQUOI UN MODULE À PART, ET PAS UNE MODIFICATION DE `ChatWidget.js`.
 * Le widget est partagé par plusieurs écrans et son fichier est en ES5 strict
 * (règle du projet). On n'y touche donc pas : ce module s'attache au bouton
 * DEPUIS LA PAGE D'ACCUEIL, par son `data-testid`. Le comportement est ainsi
 * limité au contexte demandé, et le widget garde exactement son code.
 *
 * CE QU'IL FAIT, ET CE QU'IL NE FAIT PAS.
 *   - Il déplace la BULLE FERMÉE, jamais la fenêtre de conversation ouverte.
 *   - Il distingue un TAP d'un GLISSÉ : sous le seuil, le clic passe et le
 *     chat s'ouvre comme avant ; au-delà, la bulle suit le doigt et le clic
 *     qui suit est absorbé, pour que déplacer n'ouvre pas le chat par erreur.
 *   - Il garde la bulle ENTIÈREMENT visible : les coordonnées sont bornées à
 *     une zone sûre qui tient compte des encoches (`safe-area-inset-*`).
 *   - Il mémorise la position dans `localStorage`. C'est une préférence
 *     d'interface, pas une donnée métier : rien ne part en base.
 *   - Il ne touche NI au clavier (le bouton reste un `<button>`, donc Entrée
 *     et Espace l'ouvrent), NI à l'`aria-label`, NI à la conversation.
 *
 * LE SEUIL N'EST PAS UN CHIFFRE INVENTÉ : 8 px, mesuré au doigt simulé, est
 * au-dessus du tremblement d'un tap (2-4 px) et bien en dessous d'un geste
 * de déplacement volontaire.
 */

export const CLE_BULLE = 'afroboost_bulle_chat';
const SEUIL_GLISSE = 8;      // px avant de considérer que c'est un déplacement
const MARGE = 10;            // px conservés entre la bulle et le bord

const nombre = (v) => (typeof v === 'number' && isFinite(v) ? v : null);

const lireSafeArea = () => {
  if (typeof window === 'undefined' || !window.getComputedStyle) return { b: 0 };
  try {
    const sonde = document.createElement('div');
    sonde.style.cssText = 'position:fixed;bottom:env(safe-area-inset-bottom,0px);visibility:hidden;pointer-events:none';
    document.body.appendChild(sonde);
    const b = parseFloat(window.getComputedStyle(sonde).bottom) || 0;
    document.body.removeChild(sonde);
    return { b };
  } catch (e) { return { b: 0 }; }
};

/** Ramène une position dans la zone où la bulle reste entièrement visible. */
export const borner = (x, y, l, h, vw, vh, basSur) => {
  const minX = MARGE;
  const maxX = Math.max(MARGE, vw - l - MARGE);
  const minY = MARGE;
  const maxY = Math.max(MARGE, vh - h - MARGE - (basSur || 0));
  return {
    x: Math.min(Math.max(x, minX), maxX),
    y: Math.min(Math.max(y, minY), maxY),
  };
};

export const lirePosition = () => {
  try {
    const brut = window.localStorage.getItem(CLE_BULLE);
    if (!brut) return null;
    const p = JSON.parse(brut);
    return (nombre(p && p.x) !== null && nombre(p && p.y) !== null) ? { x: p.x, y: p.y } : null;
  } catch (e) { return null; }
};

export const effacerPosition = () => {
  try { window.localStorage.removeItem(CLE_BULLE); } catch (e) { /* silencieux */ }
};

const ecrirePosition = (p) => {
  try { window.localStorage.setItem(CLE_BULLE, JSON.stringify(p)); } catch (e) { /* silencieux */ }
};

/**
 * Rend `el` déplaçable. Renvoie une fonction de nettoyage qui remet tout en
 * place : écouteurs retirés, styles posés ici effacés.
 */
export function activerBulleDeplacable(el) {
  if (!el || typeof window === 'undefined' || !window.PointerEvent) return () => {};

  const styleDorigine = el.getAttribute('style') || '';
  let glisse = false;          // le geste a-t-il dépassé le seuil ?
  let enCours = false;
  let depart = null;           // { px, py, x, y }
  /* La zone sûre est RELUE à chaque usage, pas figée à l'activation.
     Mesuré : lue une seule fois au montage, elle renvoyait parfois une
     valeur d'avant la stabilisation de la mise en page, et la position
     restaurée se retrouvait décalée de plusieurs dizaines de pixels. */
  const safeBas = () => lireSafeArea().b;

  /* TAILLE DE MISE EN PAGE, pas taille visuelle. Le bouton porte une
     transition et un `hover:scale-110` : son rectangle peint peut être plus
     grand que sa boîte réelle, et la borne calculée à partir de lui était
     alors trop serrée — mesuré à 1280×800, la position restaurée tombait
     46 px trop à gauche et 95 px trop haut. `offsetWidth/Height` ignore les
     transformations et donne la boîte qui compte ici. */
  const taille = () => ({
    l: el.offsetWidth || Math.round(el.getBoundingClientRect().width) || 56,
    h: el.offsetHeight || Math.round(el.getBoundingClientRect().height) || 56,
  });

  /** Pose une position absolue (haut/gauche) en neutralisant bas/droite. */
  const poser = (x, y) => {
    el.style.setProperty('left', x + 'px', 'important');
    el.style.setProperty('top', y + 'px', 'important');
    el.style.setProperty('right', 'auto', 'important');
    el.style.setProperty('bottom', 'auto', 'important');
  };

  const positionActuelle = () => {
    const r = el.getBoundingClientRect();
    return { x: r.left, y: r.top };
  };

  // Position mémorisée : on la restaure, bornée à l'écran d'aujourd'hui
  // (l'appareil a pu tourner, ou la fenêtre changer de taille).
  const restaurer = () => {
    const p = lirePosition();
    if (!p) return;
    const { l, h } = taille();
    const b = borner(p.x, p.y, l, h, window.innerWidth, window.innerHeight, safeBas());
    poser(b.x, b.y);
  };
  /* On restaure APRÈS la première image : au tout premier instant, le bouton
     peut ne pas être encore mis en page (taille nulle) et la fenêtre pas
     encore à ses dimensions définitives — la position se retrouvait alors
     bornée contre des valeurs provisoires. */
  if (typeof window.requestAnimationFrame === 'function') window.requestAnimationFrame(restaurer);
  else restaurer();

  const surPointerDown = (e) => {
    if (e.button !== undefined && e.button !== 0) return;
    enCours = true; glisse = false;
    const p = positionActuelle();
    depart = { px: e.clientX, py: e.clientY, x: p.x, y: p.y };
    try { el.setPointerCapture(e.pointerId); } catch (err) { /* pas bloquant */ }
  };

  const surPointerMove = (e) => {
    if (!enCours || !depart) return;
    const dx = e.clientX - depart.px;
    const dy = e.clientY - depart.py;
    if (!glisse && Math.abs(dx) + Math.abs(dy) < SEUIL_GLISSE) return;
    if (!glisse) {
      glisse = true;
      el.dataset.afGlisse = '1';
      // Le geste appartient désormais à la bulle : plus de défilement de page
      // sous le doigt, plus de sélection de texte à la souris.
      el.style.setProperty('touch-action', 'none');
      el.style.setProperty('user-select', 'none');
      el.style.setProperty('cursor', 'grabbing');
    }
    const { l, h } = taille();
    const b = borner(depart.x + dx, depart.y + dy, l, h, window.innerWidth, window.innerHeight, safeBas());
    poser(b.x, b.y);
    e.preventDefault();
  };

  const terminer = (e) => {
    if (!enCours) return;
    enCours = false;
    try { el.releasePointerCapture(e.pointerId); } catch (err) { /* pas bloquant */ }
    el.style.removeProperty('cursor');
    if (!glisse) { depart = null; return; }   // c'était un tap : le clic passe
    const p = positionActuelle();
    ecrirePosition(p);
    depart = null;
    // Le clic de fin de glissé ne doit pas ouvrir le chat. On l'absorbe une
    // fois, en phase de capture, puis on se retire : le tap suivant fonctionne.
    const absorber = (ev) => { ev.stopPropagation(); ev.preventDefault(); };
    el.addEventListener('click', absorber, { capture: true, once: true });
    // Filet : si aucun clic ne suit (certains navigateurs), on nettoie.
    window.setTimeout(() => {
      el.removeEventListener('click', absorber, { capture: true });
      delete el.dataset.afGlisse;
    }, 400);
  };

  const surResize = () => {
    if (!lirePosition()) return;
    const { l, h } = taille();
    const p = positionActuelle();
    const b = borner(p.x, p.y, l, h, window.innerWidth, window.innerHeight, safeBas());
    poser(b.x, b.y);
  };

  el.addEventListener('pointerdown', surPointerDown);
  el.addEventListener('pointermove', surPointerMove);
  el.addEventListener('pointerup', terminer);
  el.addEventListener('pointercancel', terminer);
  window.addEventListener('resize', surResize);
  el.style.setProperty('touch-action', 'none');

  return () => {
    el.removeEventListener('pointerdown', surPointerDown);
    el.removeEventListener('pointermove', surPointerMove);
    el.removeEventListener('pointerup', terminer);
    el.removeEventListener('pointercancel', terminer);
    window.removeEventListener('resize', surResize);
    el.setAttribute('style', styleDorigine);
  };
}

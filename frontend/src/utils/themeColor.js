// V259 — point unique d'application de la couleur de marque.
//
// `--primary-color` existait deja et etait posee a trois endroits d'App.js plus
// deux de ConceptEditor. La V259 y ajoute `--primary-rgb` (les trois canaux
// nus), indispensable aux styles en rgba() : `rgba(var(--primary-color), .3)`
// est invalide, seul `rgba(var(--primary-rgb), .3)` fonctionne.
//
// Les cinq appelants passent desormais par ici, pour qu'aucun ne pose une
// variable sans l'autre — un `--primary-rgb` reste sur l'ancienne couleur
// donnerait des halos roses autour de boutons violets.

// Triplet « r, g, b » d'une couleur #rrggbb (ou #rgb), ou null si illisible.
export function hexToRgbTriplet(hex) {
  if (typeof hex !== 'string') return null;
  let h = hex.trim().replace(/^#/, '');
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  if (!/^[0-9a-fA-F]{6}$/.test(h)) return null;
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16)
  ].join(', ');
}

// Pose --primary-color ET --primary-rgb sur <html>. Une valeur illisible est
// ignoree : mieux vaut garder la couleur precedente qu'un site sans accent.
export function applyPrimaryColor(hex) {
  if (typeof document === 'undefined') return;
  const rgb = hexToRgbTriplet(hex);
  if (!rgb) return;
  document.documentElement.style.setProperty('--primary-color', hex);
  document.documentElement.style.setProperty('--primary-rgb', rgb);
  document.documentElement.style.setProperty('--on-primary', onPrimary(hex)); // V630
}

// V630 — couleur du texte posé SUR un aplat de la couleur de marque (badge « fort »).
// Un coach peut choisir une couleur claire (jaune, rose pâle) : le blanc y devient
// illisible. Le blanc reste la règle (identité de marque, ex. #D91CD2 = 4,11:1) tant
// qu'il garde au moins 3:1 ; en dessous (couleur claire), texte quasi-noir.
export function onPrimary(hex) {
  const rgb = hexToRgbTriplet(hex);
  if (!rgb) return '#fff';
  const L = rgb.split(', ').map(Number).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  }).reduce((a, c, i) => a + c * [0.2126, 0.7152, 0.0722][i], 0);
  return 1.05 / (L + 0.05) >= 3 ? '#fff' : '#0a0a0a';
}

// V295 — anti-FOUC (flash de l'ancienne couleur ~1 s au chargement).
// On memorise les variables CSS du theme dans localStorage a chaque application
// des couleurs. Un petit script inline dans <head> (index.html) les repose
// AVANT le premier rendu -> plus de flash. Le backend reste la source de verite
// et rafraichit ce cache a chaque visite.
export function persistThemeColors(concept) {
  if (typeof localStorage === 'undefined' || !concept) return;
  try {
    const colors = {};
    if (concept.primaryColor) {
      colors['--primary-color'] = concept.primaryColor;
      const rgb = hexToRgbTriplet(concept.primaryColor);
      if (rgb) colors['--primary-rgb'] = rgb;
      colors['--on-primary'] = onPrimary(concept.primaryColor); // V630 : anti-FOUC du texte sur aplat
      const glowBase = concept.glowColor || concept.primaryColor;
      if (glowBase) {
        colors['--glow-color'] = glowBase + '66';
        colors['--glow-color-strong'] = glowBase + '99';
      }
    }
    if (concept.secondaryColor) colors['--secondary-color'] = concept.secondaryColor;
    if (concept.backgroundColor) colors['--background-color'] = concept.backgroundColor;
    if (Object.keys(colors).length) {
      localStorage.setItem('afroboost_theme_colors', JSON.stringify(colors));
    }
  } catch (e) { /* silencieux */ }
}

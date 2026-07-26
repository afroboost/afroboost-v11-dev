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

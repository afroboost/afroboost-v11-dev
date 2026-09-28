/**
 * V554 : heroLayout.js — disposition libre du texte du Hero (fonctions PURES).
 *
 * Donnee : `concept.heroLayout` (contrat CONTRAT_HERO_V554)
 *   null | { v: 1, desktop: null | Disposition, mobile: null | Disposition }
 *   Disposition = { title, subtitle, cta } ; chaque element null | {x, y, size[, align]}
 *   x, y = CENTRE de l'element, fraction de la largeur / hauteur de la boite `.af-hero`.
 *
 * Une disposition d'appareil `null` = MODE FLUX = le Hero historique, pixel pour
 * pixel. Aucune fonction de ce fichier ne lit `window` : l'appareil vient de la
 * LARGEUR DE LA BOITE, ce qui rend l'apercu mobile de l'editeur identique a un
 * vrai telephone.
 *
 * Toutes les fonctions sont IMMUABLES : elles ne modifient jamais leurs entrees
 * et renvoient la MEME reference quand rien ne change (utile pour ne jamais faire
 * de setState identique -> pas de boucle de rendu, cf. CLAUDE.md).
 */

export const HERO_ELEMENTS = ['title', 'subtitle', 'cta'];
export const HERO_APPAREILS = ['desktop', 'mobile'];
export const HERO_ALIGNS = ['left', 'center', 'right'];
export const HERO_SEUIL_MOBILE = 1024; // meme seuil que les anciennes `max-width: 1023px`
export const HERO_TAILLE_MIN = 0.6;
export const HERO_TAILLE_MAX = 1.8;

// V554 : ZONES SURES, en px de la boite Hero. Aucun element ne peut y entrer.
// SOURCE UNIQUE : `haut` et `bas` sont AUSSI le padding haut / bas du mode flux
// (HeroTexte les pose en style en ligne). Changer une valeur ici deplace donc
// d'un meme geste le Hero historique ET la limite de l'editeur — et garantit
// que le mode flux tient toujours dans la zone sure (aucun saut a la 1re prise).
// Valeurs = celles d'origin/main (App.css avant V554) :
// - mobile  : haut 76 = bandeau fixe du compte a rebours (64 px) + air ;
//             bas 104 = bloc coach du carrousel (avatar + nom + ligne coach).
// - desktop : haut 0 (la page reservait deja 56 px au-dessus du hero) ;
//             bas 56 = bloc coach du carrousel.
// - cote 12 (le mode flux garde son `px-6` = 24 px, donc tient dedans).
// ⚠️ INTEGRATION (barre haute reservee par la page, lot BARRE) : passer `haut`
// a 44 sur les DEUX appareils, ici et nulle part ailleurs.
export const HERO_ZONES_SURES = {
  desktop: { haut: 0, bas: 56, cote: 12 },
  mobile: { haut: 76, bas: 104, cote: 12 },
};

// V554 : positions par defaut normalisees, MESUREES sur le mode flux (build de
// origin/main, concept par defaut) : 1440x900 (hero 387 px) pour desktop,
// 390x844 (hero 473 px) pour mobile. Le CTA desktop englobe la ligne d'offre
// (« Ton premier cours est gratuit. ») qui le suit en mode positionne.
export const HERO_DEFAUTS = {
  // 1440x900 : titre centre a 78,5 px (0,203), sous-titre 146,9 (0,380),
  // bloc offre + CTA 181,3 -> 282,5 : centre 231,9 (0,599).
  desktop: {
    title: { x: 0.5, y: 0.2, size: 1, align: 'center' },
    subtitle: { x: 0.5, y: 0.38, size: 1, align: 'center' },
    cta: { x: 0.5, y: 0.6, size: 1 },
  },
  // 390x844 : titre centre a 180,4 px (0,382), CTA 273,7 (0,579). Le
  // sous-titre est masque sur telephone : son defaut est entre les deux.
  mobile: {
    title: { x: 0.5, y: 0.38, size: 1, align: 'center' },
    subtitle: { x: 0.5, y: 0.48, size: 1, align: 'center' },
    cta: { x: 0.5, y: 0.58, size: 1 },
  },
};

const estNombre = (v) => typeof v === 'number' && Number.isFinite(v);
const borne = (v, min, max) => Math.min(max, Math.max(min, v));
const arrondi = (v, n = 4) => {
  const f = Math.pow(10, n);
  return Math.round(v * f) / f;
};
const estObjet = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

export function appareilPour(largeurBoitePx) {
  return estNombre(largeurBoitePx) && largeurBoitePx >= HERO_SEUIL_MOBILE ? 'desktop' : 'mobile';
}

// ─── Normalisation : MEMES REGLES que le serveur (v554_normaliser_hero_layout) ───
// - element : x ET y nombres finis obligatoires (bool refuse), bornes [0,1] ;
//   size absente / invalide -> 1, bornee [0.6, 1.8] ; align absent / invalide ->
//   'center' (titre et sous-titre seulement ; le CTA n'a pas d'align).
// - disposition sans aucun element valide -> null.
// - les DEUX appareils null -> null tout court.
function normaliserElement(brut, el) {
  if (!estObjet(brut)) return null;
  if (!estNombre(brut.x) || !estNombre(brut.y)) return null;
  const propre = {
    x: borne(brut.x, 0, 1),
    y: borne(brut.y, 0, 1),
    size: borne(estNombre(brut.size) ? brut.size : 1, HERO_TAILLE_MIN, HERO_TAILLE_MAX),
  };
  if (el !== 'cta') {
    propre.align = typeof brut.align === 'string' && HERO_ALIGNS.includes(brut.align) ? brut.align : 'center';
  }
  return propre;
}

function normaliserDisposition(brut) {
  if (!estObjet(brut)) return null;
  const sortie = {};
  let unValide = false;
  HERO_ELEMENTS.forEach((el) => {
    sortie[el] = normaliserElement(brut[el], el);
    if (sortie[el]) unValide = true;
  });
  return unValide ? sortie : null;
}

export function normaliserLayout(brut) {
  if (!estObjet(brut)) return null;
  const desktop = normaliserDisposition(brut.desktop);
  const mobile = normaliserDisposition(brut.mobile);
  if (!desktop && !mobile) return null;
  return { v: 1, desktop, mobile };
}

// null = mode flux (rendu historique) pour cet appareil.
export function dispositionPour(layout, appareil) {
  const propre = normaliserLayout(layout);
  if (!propre) return null;
  return propre[appareil === 'desktop' ? 'desktop' : 'mobile'];
}

export function elementEffectif(layout, appareil, el) {
  const app = appareil === 'desktop' ? 'desktop' : 'mobile';
  const dispo = dispositionPour(layout, app);
  const defaut = HERO_DEFAUTS[app][el];
  const valeur = dispo && dispo[el] ? dispo[el] : defaut;
  const sortie = { x: valeur.x, y: valeur.y, size: valeur.size, align: el === 'cta' ? 'center' : valeur.align || 'center' };
  return sortie;
}

// ─── Conversions ────────────────────────────────────────────────────────────
export function normaliseVersPx(pos, largeurBoite, hauteurBoite) {
  return { x: pos.x * largeurBoite, y: pos.y * hauteurBoite };
}

export function pxVersNormalise(pos, largeurBoite, hauteurBoite) {
  return {
    x: largeurBoite > 0 ? pos.x / largeurBoite : 0.5,
    y: hauteurBoite > 0 ? pos.y / hauteurBoite : 0.5,
  };
}

// ─── Bornage ────────────────────────────────────────────────────────────────
// Entree / sortie NORMALISEES (centre). Garde TOUT l'element dans la zone sure.
// Element plus grand que la zone sur un axe -> centre dans la zone sur cet axe
// (resultat deterministe, jamais colle a un bord au hasard).
function bornerAxe(centrePx, tailleEl, debut, fin) {
  const dispo = fin - debut;
  if (tailleEl >= dispo) return debut + dispo / 2;
  return borne(centrePx, debut + tailleEl / 2, fin - tailleEl / 2);
}

export function borner(pos, largeurEl, hauteurEl, largeurBoite, hauteurBoite, appareil) {
  const zone = HERO_ZONES_SURES[appareil === 'desktop' ? 'desktop' : 'mobile'];
  if (!(largeurBoite > 0) || !(hauteurBoite > 0)) return { x: pos.x, y: pos.y };
  const px = normaliseVersPx(pos, largeurBoite, hauteurBoite);
  const x = bornerAxe(px.x, largeurEl || 0, zone.cote, largeurBoite - zone.cote);
  const y = bornerAxe(px.y, hauteurEl || 0, zone.haut, hauteurBoite - zone.bas);
  return pxVersNormalise({ x, y }, largeurBoite, hauteurBoite);
}

// ─── Modifications (immuables) ──────────────────────────────────────────────
// `positionsDepart` : { title:{x,y}, subtitle:{x,y}, cta:{x,y} } normalisees,
// MESUREES sur le mode flux (HeroTexte -> lirePositionsFlux). Quand l'appareil
// n'a pas encore de disposition, elle est creee a partir de ces mesures : les
// trois elements restent EXACTEMENT ou ils etaient -> aucun saut visuel.
function dispositionDeDepart(appareil, positionsDepart) {
  const sortie = {};
  HERO_ELEMENTS.forEach((el) => {
    const mesure = positionsDepart && positionsDepart[el];
    const base = mesure && estNombre(mesure.x) && estNombre(mesure.y) ? mesure : HERO_DEFAUTS[appareil][el];
    sortie[el] = el === 'cta'
      ? { x: arrondi(borne(base.x, 0, 1)), y: arrondi(borne(base.y, 0, 1)), size: 1 }
      : { x: arrondi(borne(base.x, 0, 1)), y: arrondi(borne(base.y, 0, 1)), size: 1, align: 'center' };
  });
  return sortie;
}

function modifierElement(layout, appareil, el, modif, positionsDepart) {
  if (!HERO_ELEMENTS.includes(el)) return layout;
  const app = appareil === 'desktop' ? 'desktop' : 'mobile';
  const propre = normaliserLayout(layout) || { v: 1, desktop: null, mobile: null };
  const dispo = propre[app] || dispositionDeDepart(app, positionsDepart);
  const courant = dispo[el] || { ...HERO_DEFAUTS[app][el] };
  const nouveau = normaliserElement({ ...courant, ...modif(courant) }, el);
  const suivant = { ...propre, [app]: { ...dispo, [el]: nouveau } };
  return layoutsEgaux(suivant, layout) ? layout : suivant;
}

export function deplacer(layout, appareil, el, pos, positionsDepart) {
  if (!pos || !estNombre(pos.x) || !estNombre(pos.y)) return layout;
  return modifierElement(layout, appareil, el, () => ({ x: arrondi(borne(pos.x, 0, 1)), y: arrondi(borne(pos.y, 0, 1)) }), positionsDepart);
}

export function changerTaille(layout, appareil, el, delta, positionsDepart) {
  if (!estNombre(delta)) return layout;
  return modifierElement(layout, appareil, el, (c) => ({ size: arrondi(borne(c.size + delta, HERO_TAILLE_MIN, HERO_TAILLE_MAX), 2) }), positionsDepart);
}

export function changerAlignement(layout, appareil, el, align, positionsDepart) {
  if (el === 'cta' || !HERO_ALIGNS.includes(align)) return layout;
  return modifierElement(layout, appareil, el, () => ({ align }), positionsDepart);
}

// L'element reprend sa position par defaut (HERO_DEFAUTS). Si plus aucun element
// n'est positionne, la disposition redevient null = mode flux (meme regle que
// le serveur, qui ecrirait null de toute facon).
export function reinitialiserElement(layout, appareil, el) {
  const app = appareil === 'desktop' ? 'desktop' : 'mobile';
  const propre = normaliserLayout(layout);
  if (!propre || !propre[app] || !propre[app][el]) return layout;
  const dispo = { ...propre[app], [el]: null };
  const vide = HERO_ELEMENTS.every((e) => !dispo[e]);
  return { ...propre, [app]: vide ? null : dispo };
}

// Retour EXACT au Hero historique sur cet appareil ; l'autre appareil est intact.
// Renvoie toujours un objet { v:1, desktop, mobile } : c'est la forme a envoyer
// au PUT /api/concept (un `null` tout court y serait ignore).
export function reinitialiserAppareil(layout, appareil) {
  const app = appareil === 'desktop' ? 'desktop' : 'mobile';
  const propre = normaliserLayout(layout) || { v: 1, desktop: null, mobile: null };
  return { ...propre, [app]: null };
}

// Egalite SEMANTIQUE : null et { v:1, desktop:null, mobile:null } sont egaux
// (les deux rendent le Hero historique).
export function layoutsEgaux(a, b) {
  const na = normaliserLayout(a);
  const nb = normaliserLayout(b);
  if (!na || !nb) return !na && !nb;
  return HERO_APPAREILS.every((app) => {
    const da = na[app];
    const db = nb[app];
    if (!da || !db) return !da && !db;
    return HERO_ELEMENTS.every((el) => {
      const ea = da[el];
      const eb = db[el];
      if (!ea || !eb) return !ea && !eb;
      return ea.x === eb.x && ea.y === eb.y && ea.size === eb.size && (ea.align || null) === (eb.align || null);
    });
  });
}

// V547 -> V554 : textes du Hero (concept.heroTitle / heroSubtitle / heroCtaLabel).
// Defauts = le texte historique, caractere pour caractere (deplaces d'App.js).
// Une valeur vide ou faite d'espaces retombe sur le defaut : un champ vide dans
// l'editeur ne laisse jamais un Hero sans titre ni un bouton muet.
export const HERO_TEXTES_DEFAUT = {
  title: 'Danse. Transpire. Lâche prise.',
  subtitle: "Vis l'expérience Afroboost : danse afrobeat et fitness au casque, même si tu n'as jamais dansé.",
  cta: 'Réserver mon 1er cours gratuit',
};
export const texteHero = (v, d) => (typeof v === 'string' && v.trim() ? v : d);

// V554 : la vitrine d'un partenaire ne doit JAMAIS heriter de la disposition
// du super-admin (le concept de l'accueil est fusionne avec celui du partenaire
// dans App.js). La disposition vient du partenaire, ou n'existe pas.
export function fusionnerConceptVitrine(precedent, conceptPartenaire) {
  const partenaire = conceptPartenaire || {};
  return {
    ...(precedent || {}),
    ...partenaire,
    heroLayout: partenaire.heroLayout !== undefined && partenaire.heroLayout !== null ? partenaire.heroLayout : null,
  };
}

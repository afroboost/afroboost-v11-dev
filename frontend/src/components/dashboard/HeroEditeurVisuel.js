// V554 : HeroEditeurVisuel — « Video Hero » devient un editeur visuel.
//
// Le coach VOIT son Hero tel qu'il sera sur la page d'accueil (meme media,
// meme bandeau haut, et surtout LE MEME composant <HeroTexte> que la page :
// jamais une copie) et y deplace au doigt / a la souris le titre, le
// sous-titre et le bouton, avec une disposition DESKTOP et une disposition
// MOBILE independantes (concept.heroLayout, contrat CONTRAT_HERO_V554).
//
// Regles tenues ici :
// - Pointer Events UNIQUEMENT (souris, doigt, stylet : une seule implementation).
// - Pendant un glissement, seul un etat LOCAL bouge (layout de travail, rythme
//   requestAnimationFrame) ; au relachement, UN SEUL setConcept -> l'auto-save
//   existant du tableau de bord (debounce 1 s, PUT /api/concept) enregistre.
//   Jamais de requete pendant le glissement.
// - Jamais de setState identique (layoutsEgaux) ; effets sur des primitives.
// - heroLayout ecrit = TOUJOURS un objet (layoutPourEnvoi).
// - Couleurs : uniquement var(--primary-color) / rgba(var(--primary-rgb)).
import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import HeroTexte from '../HeroTexte';
import SvgIcon from '../SvgIcon';
import {
  HERO_ZONES_SURES,
  borner,
  changerAlignement,
  changerTaille,
  deplacer,
  dispositionPour,
  elementEffectif,
  layoutsEgaux,
  reinitialiserAppareil,
  reinitialiserElement,
} from '../../utils/heroLayout';
import {
  APERCU_DIMENSIONS,
  PAS_TAILLE,
  aBougeAssez,
  decaler,
  directionDeTouche,
  ecartSaisie,
  layoutAEcrire,
  layoutPourEnvoi,
  libelleStatut,
  mediaApercu,
  peutAgrandir,
  peutReduire,
  pointeurVersCentre,
  pourcentageTaille,
  tailleCadre,
} from '../../utils/heroEditeur';

const LIBELLES = { title: 'Titre', subtitle: 'Sous-titre', cta: 'Bouton' };
const ELEMENTS = ['title', 'subtitle', 'cta'];

// V554 : focus visible sur tous les boutons de l'editeur (le style en ligne ne
// sait pas exprimer :focus-visible).
const CSS_EDITEUR = `
.hero-editeur-btn:focus-visible, .hero-editeur-apercu-cadre:focus-visible {
  outline: 2px solid var(--primary-color, #D91CD2);
  outline-offset: 2px;
}
.hero-editeur-btn:disabled { opacity: 0.4; cursor: not-allowed; }
`;

const styleBouton = (actif) => ({
  minWidth: 44,
  minHeight: 44,
  padding: '0 12px',
  borderRadius: 10,
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 6,
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
  color: actif ? 'var(--primary-color, #D91CD2)' : 'rgba(255,255,255,0.85)',
  background: actif ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.18)' : 'rgba(255,255,255,0.06)',
  border: `1px solid ${actif ? 'var(--primary-color, #D91CD2)' : 'rgba(255,255,255,0.15)'}`,
});

// V554 : icones d'alignement (SVG inline, stroke=currentColor).
const IconeAlign = ({ sens }) => {
  const lignes = {
    left: [[4, 6, 20, 6], [4, 10, 14, 10], [4, 14, 20, 14], [4, 18, 12, 18]],
    center: [[4, 6, 20, 6], [7, 10, 17, 10], [4, 14, 20, 14], [8, 18, 16, 18]],
    right: [[4, 6, 20, 6], [10, 10, 20, 10], [4, 14, 20, 14], [12, 18, 20, 18]],
  }[sens];
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      {lignes.map((l, i) => <line key={i} x1={l[0]} y1={l[1]} x2={l[2]} y2={l[3]} />)}
    </svg>
  );
};

const IconeAppareil = ({ appareil }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {appareil === 'desktop'
      ? (<><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></>)
      : (<><rect x="7" y="2" width="10" height="20" rx="2" /><path d="M11 18h2" /></>)}
  </svg>
);

const IconeGlobe = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" />
  </svg>
);

const IconeLogo = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M3 18v-6a9 9 0 0 1 18 0v6" />
    <path d="M21 19a2 2 0 0 1-2 2h-1v-6h3zM3 19a2 2 0 0 0 2 2h1v-6H3z" />
  </svg>
);

/* V645.4j-fix — Champ HEX avec saisie caractère par caractère */
function ChampHex({ valeur, defaut, onChange }) {
  const [brouillon, setBrouillon] = useState(valeur || defaut);
  useEffect(() => { setBrouillon(valeur || defaut); }, [valeur, defaut]);
  const valider = (v) => {
    const hex = v.startsWith('#') ? v : '#' + v;
    return /^#[0-9a-fA-F]{6}$/i.test(hex) ? hex : null;
  };
  return (
    <input
      type="text"
      value={brouillon}
      maxLength={7}
      onChange={(e) => {
        setBrouillon(e.target.value);
        const hex = valider(e.target.value);
        if (hex) onChange(hex);
      }}
      onBlur={() => {
        const hex = valider(brouillon);
        if (hex) { setBrouillon(hex); onChange(hex); }
        else setBrouillon(valeur || defaut);
      }}
      style={{ width: 64, fontSize: 10, textAlign: 'center', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 6, color: '#fff', padding: '3px 4px' }}
    />
  );
}

export default function HeroEditeurVisuel({ concept, setConcept, conceptSaveStatus }) {
  const c = concept || {};
  const [appareil, setAppareil] = useState('desktop');
  const [selection, setSelection] = useState(null);
  // Layout de TRAVAIL pendant un glissement (null hors glissement : l'apercu
  // lit alors directement concept.heroLayout — aucune copie a resynchroniser,
  // donc rien ne peut ecraser un glissement en cours).
  const [layoutGlisse, setLayoutGlisse] = useState(null);
  const [largeurDispo, setLargeurDispo] = useState(0);

  const conteneurRef = useRef(null);
  const apercuRef = useRef(null);
  const boiteRef = useRef(null);
  const heroRef = useRef(null); // rempli par HeroTexte (refsElements)
  const glisseRef = useRef(null);
  const rafRef = useRef(0);
  const layoutConceptRef = useRef(c.heroLayout);
  const dernierStatutRef = useRef('');

  useLayoutEffect(() => { layoutConceptRef.current = c.heroLayout; });
  useEffect(() => { if (conceptSaveStatus) dernierStatutRef.current = conceptSaveStatus; }, [conceptSaveStatus]);

  // Sous-titre masque sur telephone (cote page) : jamais selectionne en mobile.
  const sel = appareil === 'mobile' && selection === 'subtitle' ? null : selection;
  const dims = APERCU_DIMENSIONS[appareil];

  // ── Largeur disponible (ResizeObserver) -> echelle ──────────────────────
  useLayoutEffect(() => {
    const noeud = conteneurRef.current;
    if (!noeud) return undefined;
    const lire = () => {
      const w = Math.floor(noeud.clientWidth);
      setLargeurDispo((prev) => (prev === w ? prev : w));
    };
    lire();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(lire);
    ro.observe(noeud);
    return () => ro.disconnect();
  }, []);
  const cadre = tailleCadre(largeurDispo, appareil);

  // ── Nettoyage d'un glissement interrompu par un demontage ─────────────
  useEffect(() => () => {
    if (glisseRef.current && glisseRef.current.detacher) glisseRef.current.detacher();
    glisseRef.current = null;
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
  }, []);

  // ── Ecriture unique dans le concept (-> auto-save existant) ─────────────
  const appliquer = useCallback((calcul) => {
    setConcept((prev) => {
      const p = prev || {};
      const suivant = calcul(p.heroLayout);
      if (!suivant || layoutsEgaux(suivant, p.heroLayout)) return prev;
      return { ...p, heroLayout: layoutPourEnvoi(suivant) };
    });
  }, [setConcept]);

  const positionsActuelles = () => (heroRef.current && heroRef.current.lirePositions ? heroRef.current.lirePositions() : null);
  const modePositionne = () => {
    const h = heroRef.current;
    return !!(h && h.racine && h.racine.getAttribute('data-mode') === 'positionne');
  };
  // Dimensions (px natifs) d'un element — fiables seulement en mode positionne
  // (en mode flux le titre occupe toute la largeur, le bornage serait faux).
  const dimsElement = (el) => {
    const h = heroRef.current;
    const noeud = h && h[el];
    if (!noeud || !modePositionne()) return null;
    return { largeurEl: noeud.offsetWidth, hauteurEl: noeud.offsetHeight, largeurBoite: h.largeur, hauteurBoite: h.hauteur };
  };

  // ── Glisser (Pointer Events) ────────────────────────────────────────────
  const calculer = (g) => {
    const boite = boiteRef.current;
    if (!boite) return g.layoutCourant || g.layoutInitial;
    const centre = pointeurVersCentre(g.dernier, boite.getBoundingClientRect(), g.echelle, g.ecart, g.L, g.H);
    const h = heroRef.current;
    const noeud = h && h[g.el];
    const pos = noeud && modePositionne()
      ? borner(centre, noeud.offsetWidth, noeud.offsetHeight, g.L, g.H, g.appareil)
      : centre;
    return deplacer(g.layoutInitial, g.appareil, g.el, pos, g.positions);
  };

  const onSaisirElement = (el, evt) => {
    if (evt.pointerType === 'mouse' && evt.button !== 0) return;
    if (appareil === 'mobile' && el === 'subtitle') return;
    const boite = boiteRef.current;
    if (!boite || !heroRef.current || glisseRef.current) return;
    evt.preventDefault(); // pas de selection de texte, pas de glisser natif
    evt.stopPropagation();
    setSelection(el);
    if (apercuRef.current) {
      try { apercuRef.current.focus({ preventScroll: true }); } catch (e) { /* navigateur ancien */ }
    }
    const L = dims.largeur;
    const H = dims.hauteur;
    const rect = boite.getBoundingClientRect();
    const echelle = rect.width > 0 ? rect.width / L : 1;
    // Positions AFFICHEES (flux ou positionne) : base de la 1re disposition
    // de l'appareil -> aucun saut a la premiere prise.
    const positions = positionsActuelles();
    const centre = (positions && positions[el]) || elementEffectif(layoutConceptRef.current, appareil, el);
    const depart = { x: evt.clientX, y: evt.clientY };
    const cible = evt.currentTarget;
    try { cible.setPointerCapture(evt.pointerId); } catch (e) { /* capture impossible : les ecouteurs window suffisent */ }

    const g = {
      el,
      appareil,
      pointerId: evt.pointerId,
      depart,
      dernier: depart,
      ecart: ecartSaisie(depart, rect, echelle, centre, L, H),
      echelle,
      L,
      H,
      positions,
      layoutInitial: layoutConceptRef.current,
      layoutCourant: null,
      aGlisse: false,
    };

    const surMouvement = (e) => {
      if (e.pointerId !== g.pointerId || glisseRef.current !== g) return;
      g.dernier = { x: e.clientX, y: e.clientY };
      if (!g.aGlisse) {
        if (!aBougeAssez(g.depart, g.dernier)) return;
        g.aGlisse = true;
      }
      if (e.cancelable) e.preventDefault();
      if (rafRef.current) return;
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = 0;
        if (glisseRef.current !== g) return;
        const l = calculer(g);
        g.layoutCourant = l;
        setLayoutGlisse((prev) => (prev && layoutsEgaux(prev, l) ? prev : l));
      });
    };
    const surFin = (e) => {
      if (e.pointerId !== g.pointerId || glisseRef.current !== g) return;
      g.detacher();
      glisseRef.current = null;
      if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = 0; }
      let final = g.layoutCourant;
      if (g.aGlisse && e.type === 'pointerup') {
        g.dernier = { x: e.clientX, y: e.clientY };
        final = calculer(g);
      }
      const aEcrire = layoutAEcrire(g.layoutInitial, final, g.aGlisse);
      if (aEcrire) {
        setConcept((prev) => {
          const p = prev || {};
          return layoutsEgaux(p.heroLayout, aEcrire) ? prev : { ...p, heroLayout: aEcrire };
        });
      }
      setLayoutGlisse(null);
    };
    g.detacher = () => {
      window.removeEventListener('pointermove', surMouvement);
      window.removeEventListener('pointerup', surFin);
      window.removeEventListener('pointercancel', surFin);
    };
    window.addEventListener('pointermove', surMouvement, { passive: false });
    window.addEventListener('pointerup', surFin);
    window.addEventListener('pointercancel', surFin);
    glisseRef.current = g;
  };

  // Clic dans une zone vide de l'apercu : deselectionne.
  const surAppuiBoite = (evt) => {
    if (evt.target && evt.target.closest && evt.target.closest('[data-hero-el]')) return;
    setSelection((prev) => (prev === null ? prev : null));
  };

  // ── Reglages (chaque action = un setConcept) ──────────────────────────
  const flecher = (direction, maj) => {
    if (!sel) return;
    const pos = positionsActuelles();
    const d = dimsElement(sel);
    appliquer((l) => decaler(l, appareil, sel, direction, maj, pos, d));
  };
  const retailler = (signe) => {
    if (!sel) return;
    const pos = positionsActuelles();
    appliquer((l) => changerTaille(l, appareil, sel, signe * PAS_TAILLE, pos));
  };
  const aligner = (align) => {
    if (!sel || sel === 'cta') return;
    const pos = positionsActuelles();
    appliquer((l) => changerAlignement(l, appareil, sel, align, pos));
  };
  const reinitElement = () => { if (sel) appliquer((l) => reinitialiserElement(l, appareil, sel)); };
  const reinitLayout = () => appliquer((l) => reinitialiserAppareil(l, appareil));

  // V645.4j — gradient titre + espacement lignes (stockés dans concept, pas heroLayout)
  const GRADIENT_DEFAUT = { actif: true, debut: '#D91CD2', milieu: '#A527D2', fin: '#7021B8', direction: 110 };
  const gTitre = c.heroGradientTitre || GRADIENT_DEFAUT;
  const lineGapActuel = c.heroTitreLineGap != null ? c.heroTitreLineGap : 0;

  // V645.4k — typographie du titre. `null` = valeur par défaut du thème, de
  // sorte qu'un concept existant rende exactement comme avant.
  const letterSpacingActuel = c.heroTitreLetterSpacing != null ? c.heroTitreLetterSpacing : null;
  const lineHeightActuel = c.heroTitreLineHeight != null ? c.heroTitreLineHeight : null;

  /* V645.4k — ANNULER / RÉTABLIR.
     L'historique ne garde que les réglages typographiques du Hero : il ne peut
     donc pas réécrire par mégarde une autre partie du concept. On empile AVANT
     la mutation, pendant le rendu, plutôt que dans l'updateur de setConcept —
     un effet de bord dans un updateur serait rejoué en mode strict. */
  const CLES_HERO = ['heroGradientTitre', 'heroTitreLineGap', 'heroTitreLetterSpacing', 'heroTitreLineHeight'];
  const instantane = (o) => CLES_HERO.reduce((acc, k) => { acc[k] = o ? o[k] : undefined; return acc; }, {});
  const histoRef = useRef({ passe: [], futur: [] });
  const [histoLen, setHistoLen] = useState({ p: 0, f: 0 });
  const majHistoLen = () => {
    const h = histoRef.current;
    setHistoLen((prev) => (prev.p === h.passe.length && prev.f === h.futur.length
      ? prev
      : { p: h.passe.length, f: h.futur.length }));
  };
  const pousserHistorique = () => {
    const h = histoRef.current;
    h.passe.push(instantane(c));
    if (h.passe.length > 50) h.passe.shift();
    h.futur = [];
    majHistoLen();
  };
  const annuler = () => {
    const h = histoRef.current;
    if (!h.passe.length) return;
    const avant = h.passe.pop();
    h.futur.push(instantane(c));
    majHistoLen();
    setConcept((prev) => ({ ...(prev || {}), ...avant }));
  };
  const retablir = () => {
    const h = histoRef.current;
    if (!h.futur.length) return;
    const apres = h.futur.pop();
    h.passe.push(instantane(c));
    majHistoLen();
    setConcept((prev) => ({ ...(prev || {}), ...apres }));
  };

  const majGradient = (update) => {
    pousserHistorique();
    setConcept((prev) => {
      const p2 = prev || {};
      const next = { ...GRADIENT_DEFAUT, ...(p2.heroGradientTitre || {}), ...update };
      return { ...p2, heroGradientTitre: next };
    });
  };
  const majLineGap = (delta) => {
    pousserHistorique();
    setConcept((prev) => {
      const p2 = prev || {};
      const actuel = p2.heroTitreLineGap != null ? p2.heroTitreLineGap : 0;
      const prochain = Math.round(Math.max(-24, Math.min(32, actuel + delta)));
      if (prochain === actuel) return prev;
      return { ...p2, heroTitreLineGap: prochain };
    });
  };
  const majLetterSpacing = (delta) => {
    pousserHistorique();
    setConcept((prev) => {
      const p2 = prev || {};
      const actuel = p2.heroTitreLetterSpacing != null ? p2.heroTitreLetterSpacing : 0;
      const prochain = Math.round(Math.max(-8, Math.min(16, actuel + delta)));
      if (prochain === actuel) return prev;
      return { ...p2, heroTitreLetterSpacing: prochain };
    });
  };
  const majLineHeight = (delta) => {
    pousserHistorique();
    setConcept((prev) => {
      const p2 = prev || {};
      const actuel = p2.heroTitreLineHeight != null ? p2.heroTitreLineHeight : 1.25;
      const prochain = Math.round(Math.max(0.8, Math.min(2, actuel + delta)) * 100) / 100;
      if (prochain === actuel) return prev;
      return { ...p2, heroTitreLineHeight: prochain };
    });
  };
  const reinitGradient = () => {
    pousserHistorique();
    setConcept((prev) => {
      const p2 = prev || {};
      return {
        ...p2,
        heroGradientTitre: GRADIENT_DEFAUT,
        heroTitreLineGap: 0,
        heroTitreLetterSpacing: null,
        heroTitreLineHeight: null,
      };
    });
  };

  const surTouche = (evt) => {
    if (evt.key === 'Escape') { setSelection((prev) => (prev === null ? prev : null)); return; }
    const direction = directionDeTouche(evt.key);
    if (!direction || !sel) return;
    evt.preventDefault();
    flecher(direction, evt.shiftKey);
  };

  // ── Donnees d'affichage ────────────────────────────────────────────────
  const conceptApercu = layoutGlisse ? { ...c, heroLayout: layoutGlisse } : c;
  const layoutAffiche = conceptApercu.heroLayout;
  const dispoAppareil = dispositionPour(c.heroLayout, appareil);
  const eff = sel ? elementEffectif(layoutAffiche, appareil, sel) : null;
  const elementPositionne = !!(sel && dispoAppareil && dispoAppareil[sel]);
  const media = mediaApercu(c);
  const zones = HERO_ZONES_SURES[appareil];
  const enGlissement = !!layoutGlisse;
  const statut = libelleStatut(conceptSaveStatus) || (dernierStatutRef.current === 'saved' ? 'Enregistré' : '');
  const nomAppareil = appareil === 'desktop' ? 'Desktop' : 'Mobile';

  const voile = { position: 'absolute', pointerEvents: 'none', zIndex: 6, background: 'repeating-linear-gradient(45deg, rgba(0,0,0,0.45) 0 6px, rgba(255,255,255,0.08) 6px 12px)' };

  return (
    <div
      data-testid="hero-editeur"
      style={{
        marginTop: 12, padding: 12, borderRadius: 10,
        background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.05)',
        border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.2)',
        maxWidth: '100%', overflow: 'hidden',
      }}
    >
      <style>{CSS_EDITEUR}</style>

      {/* En-tete : titre + appareil + statut */}
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 6 }}>
        <p style={{ color: 'var(--primary-color, #D91CD2)', fontSize: 13, fontWeight: 700, margin: 0 }}>Mise en page du Hero</p>
        <span
          data-testid="hero-editeur-statut"
          aria-live="polite"
          style={{ fontSize: 11, color: conceptSaveStatus === 'error' ? 'rgba(248,113,113,0.95)' : 'rgba(255,255,255,0.55)', minHeight: 16 }}
        >
          {statut}
        </span>
      </div>
      <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: 11, margin: '0 0 8px' }}>
        Faites glisser le titre, le sous-titre ou le bouton. Desktop et Mobile se règlent séparément.
      </p>

      <div role="group" aria-label="Appareil" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
        {['desktop', 'mobile'].map((a) => (
          <button
            key={a}
            type="button"
            className="hero-editeur-btn"
            data-testid={`hero-editeur-appareil-${a}`}
            aria-pressed={appareil === a}
            onClick={() => setAppareil((prev) => (prev === a ? prev : a))}
            style={styleBouton(appareil === a)}
          >
            <IconeAppareil appareil={a} />
            {a === 'desktop' ? 'Desktop' : 'Mobile'}
          </button>
        ))}
      </div>

      {/* Apercu : boite native mise a l'echelle */}
      <div ref={conteneurRef} style={{ width: '100%' }}>
        <div
          ref={apercuRef}
          data-testid="hero-editeur-apercu"
          className="hero-editeur-apercu-cadre"
          tabIndex={0}
          role="application"
          aria-label={`Aperçu du Hero (${nomAppareil}). Flèches du clavier pour déplacer l'élément sélectionné, Maj pour aller plus vite.`}
          onKeyDown={surTouche}
          data-echelle={cadre.echelle}
          style={{
            position: 'relative',
            width: cadre.largeur,
            height: cadre.hauteur,
            margin: '0 auto',
            overflow: 'hidden',
            borderRadius: 10,
            border: '1px solid rgba(255,255,255,0.12)',
          }}
        >
          <div
            ref={boiteRef}
            data-hero-boite=""
            onPointerDown={surAppuiBoite}
            style={{
              position: 'absolute',
              left: 0,
              top: 0,
              width: dims.largeur,
              height: dims.hauteur,
              transform: `scale(${cadre.echelle || 0})`,
              transformOrigin: '0 0',
              overflow: 'hidden',
              background: 'black',
              userSelect: 'none',
              WebkitUserSelect: 'none',
            }}
          >
            {media.type === 'image' && (
              <img
                key={media.url}
                src={media.url}
                alt=""
                draggable={false}
                onError={(e) => { e.currentTarget.style.display = 'none'; }}
                style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', objectPosition: '50% 30%', pointerEvents: 'none' }}
              />
            )}
            {media.type === 'video' && (
              <video
                key={media.url}
                src={media.url}
                muted
                loop
                autoPlay
                playsInline
                style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', objectPosition: '50% 30%', pointerEvents: 'none' }}
              />
            )}

            {/* Bande haute : imite le header du carrousel (decoratif). */}
            <div
              aria-hidden="true"
              style={{ position: 'absolute', left: 0, right: 0, top: 0, height: 36, zIndex: 7, pointerEvents: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white' }}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, fontWeight: 700, textShadow: '0 1px 2px rgba(0,0,0,0.5)' }}>
                <IconeLogo />Afroboost
              </span>
              <span style={{ position: 'absolute', right: 12, top: 4, width: 28, height: 28, borderRadius: '50%', background: 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <IconeGlobe />
              </span>
            </div>

            <HeroTexte
              concept={conceptApercu}
              appareil={appareil}
              modeEdition
              selection={sel}
              onSaisirElement={onSaisirElement}
              refsElements={heroRef}
            />

            {/* Pendant un deplacement : voile sur les zones interdites. */}
            {enGlissement && (
              <>
                <div data-hero-zone="haut" style={{ ...voile, left: 0, right: 0, top: 0, height: zones.haut }} />
                <div data-hero-zone="bas" style={{ ...voile, left: 0, right: 0, bottom: 0, height: zones.bas }} />
                <div data-hero-zone="gauche" style={{ ...voile, left: 0, top: zones.haut, bottom: zones.bas, width: zones.cote }} />
                <div data-hero-zone="droite" style={{ ...voile, right: 0, top: zones.haut, bottom: zones.bas, width: zones.cote }} />
              </>
            )}
          </div>
        </div>
      </div>

      {/* Choix de l'element sans glisser */}
      <div role="group" aria-label="Élément à régler" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
        {ELEMENTS.map((el) => {
          const masque = appareil === 'mobile' && el === 'subtitle';
          return (
            <button
              key={el}
              type="button"
              className="hero-editeur-btn"
              data-testid={`hero-editeur-choisir-${el}`}
              aria-pressed={sel === el}
              disabled={masque}
              title={masque ? 'Le sous-titre est masqué sur téléphone' : undefined}
              onClick={() => setSelection((prev) => (prev === el ? prev : el))}
              style={styleBouton(sel === el)}
            >
              {LIBELLES[el]}
              {masque && <span style={{ fontSize: 10, fontWeight: 400, opacity: 0.8 }}>· masqué sur téléphone</span>}
            </button>
          );
        })}
      </div>

      {/* Reglages de l'element selectionne */}
      {sel && eff && (
        <div
          role="toolbar"
          aria-label={`Réglages : ${LIBELLES[sel]}`}
          data-testid="hero-editeur-barre"
          style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginTop: 10, padding: 8, borderRadius: 10, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)' }}
        >
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <button type="button" className="hero-editeur-btn" data-testid="hero-editeur-taille-moins" aria-label="Réduire la taille" disabled={!peutReduire(eff.size)} onClick={() => retailler(-1)} style={styleBouton(false)}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><line x1="5" y1="12" x2="19" y2="12" /></svg>
            </button>
            <span aria-live="polite" style={{ minWidth: 52, textAlign: 'center', color: 'white', fontSize: 13, fontWeight: 600 }}>{pourcentageTaille(eff.size)}</span>
            <button type="button" className="hero-editeur-btn" data-testid="hero-editeur-taille-plus" aria-label="Augmenter la taille" disabled={!peutAgrandir(eff.size)} onClick={() => retailler(1)} style={styleBouton(false)}>
              <SvgIcon name="plus" size={16} />
            </button>
          </div>

          {sel !== 'cta' && (
            <div role="group" aria-label="Alignement du texte" style={{ display: 'inline-flex', gap: 4 }}>
              {[['left', 'Aligner à gauche'], ['center', 'Centrer'], ['right', 'Aligner à droite']].map(([a, libelle]) => (
                <button
                  key={a}
                  type="button"
                  className="hero-editeur-btn"
                  data-testid={`hero-editeur-align-${a}`}
                  aria-label={libelle}
                  aria-pressed={eff.align === a}
                  onClick={() => aligner(a)}
                  style={styleBouton(eff.align === a)}
                >
                  <IconeAlign sens={a} />
                </button>
              ))}
            </div>
          )}

          <div role="group" aria-label="Déplacer (Maj : plus vite)" style={{ display: 'inline-flex', gap: 4 }}>
            {[['haut', 'arrowUp', 'Monter'], ['bas', 'arrowDown', 'Descendre'], ['gauche', 'arrowLeft', 'Vers la gauche'], ['droite', 'arrowRight', 'Vers la droite']].map(([d, icone, libelle]) => (
              <button
                key={d}
                type="button"
                className="hero-editeur-btn"
                data-testid={`hero-editeur-fleche-${d}`}
                aria-label={libelle}
                title={`${libelle} (Maj : 5 %)`}
                onClick={(e) => flecher(d, e.shiftKey)}
                style={styleBouton(false)}
              >
                <SvgIcon name={icone} size={16} />
              </button>
            ))}
          </div>

          <button
            type="button"
            className="hero-editeur-btn"
            data-testid="hero-editeur-reset-element"
            disabled={!elementPositionne}
            onClick={reinitElement}
            style={styleBouton(false)}
          >
            <SvgIcon name="undo" size={16} />
            Réinitialiser cet élément
          </button>
        </div>
      )}

      {/* V645.4j — Panneau gradient + espacement inter-lignes (titre uniquement) */}
      {sel === 'title' && (
        <div
          data-testid="hero-editeur-gradient-panel"
          style={{ marginTop: 10, padding: 10, borderRadius: 10, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '.06em' }}>Gradient « LÂCHE PRISE. »</span>
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                type="button"
                className="hero-editeur-btn"
                data-testid="hero-editeur-gradient-toggle"
                aria-pressed={gTitre.actif !== false}
                onClick={() => majGradient({ actif: gTitre.actif === false ? true : false })}
                style={styleBouton(gTitre.actif !== false)}
                title="Activer / désactiver le dégradé"
              >
                {gTitre.actif !== false ? 'Activé' : 'Désactivé'}
              </button>
              <button
                type="button"
                className="hero-editeur-btn"
                data-testid="hero-editeur-gradient-reset"
                onClick={reinitGradient}
                style={styleBouton(false)}
                title="Rétablir le gradient Afroboost par défaut"
              >
                <SvgIcon name="refresh" size={13} />
              </button>
            </div>
          </div>

          {gTitre.actif !== false && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-start' }}>
              {/* Couleurs */}
              {[
                ['debut', 'Départ', '#D91CD2'],
                ['milieu', 'Milieu (opt.)', '#A527D2'],
                ['fin', 'Fin', '#7021B8'],
              ].map(([champ, libelle, defautChamp]) => (
                <div key={champ} style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'center' }}>
                  <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.45)' }}>{libelle}</span>
                  <input
                    type="color"
                    value={gTitre[champ] || defautChamp}
                    onChange={(e) => majGradient({ [champ]: e.target.value })}
                    style={{ width: 36, height: 36, padding: 2, borderRadius: 8, border: '1px solid rgba(255,255,255,0.15)', background: 'transparent', cursor: 'pointer' }}
                    data-testid={`hero-gradient-${champ}`}
                    title={`Couleur ${libelle}`}
                  />
                  <ChampHex
                    valeur={gTitre[champ]}
                    defaut={defautChamp}
                    onChange={(hex) => majGradient({ [champ]: hex })}
                  />
                </div>
              ))}

              {/* Direction */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 80 }}>
                <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.45)' }}>Direction ({gTitre.direction || 110}°)</span>
                <input
                  type="range"
                  min={0} max={360}
                  value={gTitre.direction != null ? gTitre.direction : 110}
                  onChange={(e) => majGradient({ direction: Number(e.target.value) })}
                  style={{ width: 80 }}
                  data-testid="hero-gradient-direction"
                />
              </div>
            </div>
          )}

          {/* Espacement inter-lignes du titre */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
            <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.45)', whiteSpace: 'nowrap' }}>Espace inter-lignes</span>
            <button type="button" className="hero-editeur-btn" onClick={() => majLineGap(-2)} style={styleBouton(false)} aria-label="Rapprocher les lignes" title="Rapprocher">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="5" y1="12" x2="19" y2="12"/></svg>
            </button>
            <span style={{ minWidth: 40, textAlign: 'center', color: 'white', fontSize: 12, fontWeight: 600 }}>{lineGapActuel >= 0 ? `+${lineGapActuel}` : lineGapActuel}px</span>
            <button type="button" className="hero-editeur-btn" onClick={() => majLineGap(2)} style={styleBouton(false)} aria-label="Écarter les lignes" title="Écarter">
              <SvgIcon name="plus" size={14} />
            </button>
          </div>

          {/* V645.4k — Espacement des lettres */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
            <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.45)', whiteSpace: 'nowrap' }}>Espace des lettres</span>
            <button type="button" className="hero-editeur-btn" data-testid="hero-letterspacing-moins" onClick={() => majLetterSpacing(-1)} style={styleBouton(false)} aria-label="Resserrer les lettres" title="Resserrer">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="5" y1="12" x2="19" y2="12"/></svg>
            </button>
            <span data-testid="hero-letterspacing-valeur" style={{ minWidth: 40, textAlign: 'center', color: 'white', fontSize: 12, fontWeight: 600 }}>
              {letterSpacingActuel == null ? 'Auto' : `${letterSpacingActuel > 0 ? '+' : ''}${letterSpacingActuel}px`}
            </span>
            <button type="button" className="hero-editeur-btn" data-testid="hero-letterspacing-plus" onClick={() => majLetterSpacing(1)} style={styleBouton(false)} aria-label="Écarter les lettres" title="Écarter">
              <SvgIcon name="plus" size={14} />
            </button>
          </div>

          {/* V645.4k — Interligne */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
            <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.45)', whiteSpace: 'nowrap' }}>Interligne</span>
            <button type="button" className="hero-editeur-btn" data-testid="hero-lineheight-moins" onClick={() => majLineHeight(-0.05)} style={styleBouton(false)} aria-label="Réduire l'interligne" title="Réduire">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="5" y1="12" x2="19" y2="12"/></svg>
            </button>
            <span data-testid="hero-lineheight-valeur" style={{ minWidth: 40, textAlign: 'center', color: 'white', fontSize: 12, fontWeight: 600 }}>
              {lineHeightActuel == null ? 'Auto' : lineHeightActuel.toFixed(2)}
            </span>
            <button type="button" className="hero-editeur-btn" data-testid="hero-lineheight-plus" onClick={() => majLineHeight(0.05)} style={styleBouton(false)} aria-label="Augmenter l'interligne" title="Augmenter">
              <SvgIcon name="plus" size={14} />
            </button>
          </div>

          {/* V645.4k — Annuler / Rétablir (réglages typographiques du Hero) */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
            <button type="button" className="hero-editeur-btn" data-testid="hero-annuler" onClick={annuler} disabled={histoLen.p === 0} style={{ ...styleBouton(false), opacity: histoLen.p === 0 ? 0.35 : 1, cursor: histoLen.p === 0 ? 'default' : 'pointer' }} aria-label="Annuler" title="Annuler">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 7v6h6" /><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13" /></svg>
              <span style={{ marginLeft: 6, fontSize: 11 }}>Annuler</span>
            </button>
            <button type="button" className="hero-editeur-btn" data-testid="hero-retablir" onClick={retablir} disabled={histoLen.f === 0} style={{ ...styleBouton(false), opacity: histoLen.f === 0 ? 0.35 : 1, cursor: histoLen.f === 0 ? 'default' : 'pointer' }} aria-label="Rétablir" title="Rétablir">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 7v6h-6" /><path d="M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3L21 13" /></svg>
              <span style={{ marginLeft: 6, fontSize: 11 }}>Rétablir</span>
            </button>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginTop: 10 }}>
        <button
          type="button"
          className="hero-editeur-btn"
          data-testid="hero-editeur-reset-layout"
          disabled={!dispoAppareil}
          onClick={reinitLayout}
          style={styleBouton(false)}
        >
          <SvgIcon name="refresh" size={16} />
          {`Réinitialiser la mise en page (${nomAppareil})`}
        </button>
        {!sel && (
          <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)' }}>
            Touchez un élément de l'aperçu pour le sélectionner.
          </span>
        )}
      </div>
    </div>
  );
}

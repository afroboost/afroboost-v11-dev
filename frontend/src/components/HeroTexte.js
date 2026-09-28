// V554 : HeroTexte — LE renderer unique du texte du Hero (titre, sous-titre,
// ligne d'offre, CTA). Utilise par la page d'accueil (App.js) ET par l'apercu
// de l'editeur visuel : ce que le coach voit dans l'editeur est, par
// construction, ce que le visiteur verra.
//
// DEUX MODES, par appareil (contrat CONTRAT_HERO_V554) :
// - FLUX (concept.heroLayout absent, ou disposition de l'appareil null) : le
//   Hero historique, memes classes, memes textes, meme lien, meme mesure
//   PostHog. Les anciennes media queries `max-width: 1023px` sont devenues des
//   regles `[data-appareil="mobile"]` (App.css) : l'appareil vient de la
//   LARGEUR DE LA BOITE, jamais de la fenetre — l'apercu mobile affiche sur un
//   ecran d'ordinateur est donc identique a un vrai telephone. Les tailles de
//   police `clamp(…, Nvw, …)` sont calculees ici depuis cette largeur.
// - POSITIONNE : chaque element en absolu, centre en (x·L, y·H), puis BORNE
//   dans la zone sure (borner()) apres mesure. Le bornage est fait ici, donc a
//   l'identique dans l'apercu et sur l'accueil.
//
// ⚠️ `pointer-events: none` sur le conteneur : le carrousel dessous a ses
// propres zones cliquables. Seul le CTA (et, en edition, chaque element)
// reactive les clics.
import React, { useCallback, useLayoutEffect, useRef, useState } from 'react';
import SvgIcon from './SvgIcon';
import { funnelTracer } from '../utils/funnelEssai';
import {
  HERO_ELEMENTS,
  HERO_DEFAUTS,
  HERO_TEXTES_DEFAUT,
  HERO_ZONES_SURES,
  appareilPour,
  borner,
  dispositionPour,
  elementEffectif,
  pxVersNormalise,
  texteHero,
} from '../utils/heroLayout';

const HREF_ESSAI = '/?link=b83914b4-c5a';
const SCRIM = 'linear-gradient(to bottom, rgba(0,0,0,0) 12%, rgba(0,0,0,0.5) 34%, rgba(0,0,0,0.5) 66%, rgba(0,0,0,0) 88%)';
const clamp = (min, v, max) => Math.min(max, Math.max(min, v));

// Equivalents « boite » des anciens clamp(rem, vw, rem) (1rem = 16 px).
export const policesHero = (L) => ({
  title: clamp(28, 0.06 * L, 48),        // clamp(1.75rem, 6vw, 3rem)
  subtitle: clamp(15.2, 0.034 * L, 17.6), // clamp(0.95rem, 3.4vw, 1.1rem)
  cta: clamp(15.2, 0.036 * L, 16.8),      // clamp(0.95rem, 3.6vw, 1.05rem)
});

function rectDe(el, base) {
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (!(r.width > 0) || !(r.height > 0)) return null; // masque (display:none)
  return { left: r.left - base.left, top: r.top - base.top, right: r.right - base.left, bottom: r.bottom - base.top };
}

/**
 * V554 : positions ACTUELLES (normalisees, centre) des trois elements, lues
 * dans le DOM rendu — en mode flux comme en mode positionne. C'est la source
 * de `positionsDepart` pour `deplacer()` : la premiere prise d'un element cree
 * la disposition la ou le texte se trouve deja, sans aucun saut.
 * En desktop, le CTA englobe la ligne d'offre qui le precede (en mode
 * positionne, elles bougent ensemble). Un element masque (sous-titre sur
 * mobile) prend sa position par defaut.
 * @param {HTMLElement} racine  le conteneur rendu par HeroTexte ([data-hero-racine])
 */
export function lirePositionsFlux(racine) {
  if (!racine) return null;
  const base = racine.getBoundingClientRect();
  const L = base.width;
  const H = base.height;
  const appareil = racine.getAttribute('data-appareil') === 'desktop' ? 'desktop' : 'mobile';
  const q = (s) => racine.querySelector(s);
  const sortie = {};
  HERO_ELEMENTS.forEach((el) => {
    let r = rectDe(q(`[data-hero-el="${el}"]`), base);
    if (el === 'cta' && r) {
      const offre = rectDe(q('.af-hero-offre'), base);
      if (offre) {
        r = { left: Math.min(r.left, offre.left), top: Math.min(r.top, offre.top), right: Math.max(r.right, offre.right), bottom: Math.max(r.bottom, offre.bottom) };
      }
    }
    if (!r || !(L > 0) || !(H > 0)) {
      const d = HERO_DEFAUTS[appareil][el];
      sortie[el] = { x: d.x, y: d.y };
      return;
    }
    const n = pxVersNormalise({ x: (r.left + r.right) / 2, y: (r.top + r.bottom) / 2 }, L, H);
    sortie[el] = { x: Math.round(n.x * 10000) / 10000, y: Math.round(n.y * 10000) / 10000 };
  });
  return sortie;
}

/**
 * Props :
 * - concept           : le concept (heroTitle, heroSubtitle, heroCtaLabel, heroLayout)
 * - appareil?         : 'mobile' | 'desktop' — force l'appareil (sinon : largeur de la boite)
 * - modeEdition?      : true dans l'editeur (elements saisissables, CTA inerte)
 * - selection?        : 'title' | 'subtitle' | 'cta' | null — element entoure
 * - onSaisirElement?  : (el, evt) => void, appele au pointerdown d'un element en edition
 * - refsElements?     : ref objet ; recoit { racine, title, subtitle, offre, cta,
 *                       appareil, largeur, hauteur, lirePositions() }
 */
export default function HeroTexte({ concept, appareil: appareilForce, modeEdition = false, selection = null, onSaisirElement, refsElements }) {
  const c = concept || {};
  const racineRef = useRef(null);
  const elRefs = useRef({ title: null, subtitle: null, offre: null, cta: null });
  const [boite, setBoite] = useState({ L: 0, H: 0 });
  const [centres, setCentres] = useState(null); // { el: {x,y} } normalises, bornes

  const L = boite.L;
  const H = boite.H;
  const appareil = appareilForce === 'mobile' || appareilForce === 'desktop' ? appareilForce : appareilPour(L);
  const mobile = appareil === 'mobile';
  const dispo = dispositionPour(c.heroLayout, appareil);
  const positionne = !!dispo;
  // Cle PRIMITIVE de la disposition : les effets n'en dependent jamais par objet.
  const cleDispo = positionne ? JSON.stringify(dispo) : '';
  const polices = policesHero(L);

  // ── Mesure de la boite (ResizeObserver) ─────────────────────────────────
  useLayoutEffect(() => {
    const racine = racineRef.current;
    if (!racine) return undefined;
    const lire = () => {
      const w = racine.clientWidth;
      const h = racine.clientHeight;
      setBoite((prev) => (prev.L === w && prev.H === h ? prev : { L: w, H: h }));
    };
    lire();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(lire);
    ro.observe(racine);
    return () => ro.disconnect();
  }, []);

  // ── Bornage apres mesure (mode positionne) ───────────────────────────────
  const recalculer = useCallback(() => {
    if (!positionne || !(L > 0) || !(H > 0)) {
      setCentres((prev) => (prev === null ? prev : null));
      return;
    }
    const layout = c.heroLayout;
    const suivant = {};
    HERO_ELEMENTS.forEach((el) => {
      const noeud = elRefs.current[el];
      const brut = elementEffectif(layout, appareil, el);
      const w = noeud ? noeud.offsetWidth : 0;
      const h = noeud ? noeud.offsetHeight : 0;
      suivant[el] = borner({ x: brut.x, y: brut.y }, w, h, L, H, appareil);
    });
    setCentres((prev) => {
      // Comparaison en px (demi-pixel) : aucun setState si rien ne bouge.
      if (prev && HERO_ELEMENTS.every((el) => prev[el]
        && Math.abs((prev[el].x - suivant[el].x) * L) < 0.5
        && Math.abs((prev[el].y - suivant[el].y) * H) < 0.5)) return prev;
      return suivant;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [positionne, cleDispo, appareil, L, H]);

  useLayoutEffect(() => {
    recalculer();
  });

  useLayoutEffect(() => {
    if (!positionne || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(() => recalculer());
    HERO_ELEMENTS.forEach((el) => { if (elRefs.current[el]) ro.observe(elRefs.current[el]); });
    return () => ro.disconnect();
  }, [positionne, recalculer]);

  // ── Exposition a l'editeur ───────────────────────────────────────────────
  useLayoutEffect(() => {
    if (!refsElements) return;
    refsElements.current = {
      racine: racineRef.current,
      title: elRefs.current.title,
      subtitle: elRefs.current.subtitle,
      offre: elRefs.current.offre,
      cta: elRefs.current.cta,
      appareil,
      largeur: L,
      hauteur: H,
      lirePositions: () => lirePositionsFlux(racineRef.current),
    };
  });

  // ── Edition ───────────────────────────────────────────────────────────────
  const propsEdition = (el) => {
    if (!modeEdition) return {};
    const choisi = selection === el;
    return {
      onPointerDown: (evt) => { if (onSaisirElement) onSaisirElement(el, evt); },
      styleEdition: {
        pointerEvents: 'auto',
        touchAction: 'none',
        userSelect: 'none',
        WebkitUserSelect: 'none',
        cursor: 'move',
        outline: choisi ? '2px dashed var(--primary-color, #D91CD2)' : '1px dashed rgba(255,255,255,0.35)',
        outlineOffset: 4,
      },
    };
  };
  const pe = (el) => {
    const p = propsEdition(el);
    return { onPointerDown: p.onPointerDown, style: p.styleEdition || {} };
  };

  const clicCta = (evt) => {
    if (modeEdition) { evt.preventDefault(); return; }
    // C1 : `trial_cta_click` explicite. `autocapture` reste a false.
    // C16-pre — POURQUOI `transport: 'sendBeacon'` : `config.request_batching`
    // est a true, le SDK met l'evenement en FILE ; or ce clic declenche
    // immediatement la navigation native vers le tunnel, qui annulait la
    // requete en vol. `sendBeacon` survit au dechargement de la page (API
    // verifiee : `capture.length === 3`, requete `initiatorType: "beacon"`).
    // ⚠️ Jamais de `preventDefault` hors edition : la navigation reste native
    // et immediate, la mesure est un BONUS, jamais une condition. `funnelTracer`
    // porte le try/catch et le filtre de donnees personnelles.
    // `variante: 'chat'` decrit la DESTINATION du CTA (le tunnel) : le jour ou
    // il pointera sur l'offre, elle devra devenir 'direct'.
    funnelTracer('trial_cta_click', { source: 'homepage_hero', variante: 'chat' }, { transport: 'sendBeacon' });
  };

  const titre = texteHero(c.heroTitle, HERO_TEXTES_DEFAUT.title);
  const sousTitre = texteHero(c.heroSubtitle, HERO_TEXTES_DEFAUT.subtitle);
  const libelleCta = texteHero(c.heroCtaLabel, HERO_TEXTES_DEFAUT.cta);
  const setRef = (el) => (n) => { elRefs.current[el] = n; };

  // ═══════════════════ MODE FLUX : le Hero historique ═══════════════════
  if (!positionne) {
    const ctaLarge = L >= 768; // ancien `md:` Tailwind (768 px), rapporte a la boite
    const peTitre = pe('title');
    const peSous = pe('subtitle');
    const peCta = pe('cta');
    return (
      <div
        ref={racineRef}
        data-hero-racine=""
        data-appareil={appareil}
        data-mode="flux"
        className="absolute inset-0 flex flex-col items-center justify-center text-center px-6 af-hero-texte"
        style={{
          pointerEvents: 'none',
          zIndex: 5,
          background: SCRIM,
          // V554 : reserves haute / basse = HERO_ZONES_SURES (source unique).
          paddingTop: HERO_ZONES_SURES[appareil].haut,
          paddingBottom: HERO_ZONES_SURES[appareil].bas,
        }}
      >
        <h1
          ref={setRef('title')}
          data-hero-el="title"
          onPointerDown={peTitre.onPointerDown}
          className="text-white font-extrabold leading-tight"
          style={{ fontSize: `${polices.title}px`, textShadow: '0 2px 14px rgba(0,0,0,0.75)', ...peTitre.style }}
        >
          {titre}
        </h1>
        {/* V541 : masque sur telephone par `[data-appareil="mobile"] .af-hero-sous`. */}
        <p
          ref={setRef('subtitle')}
          data-hero-el="subtitle"
          onPointerDown={peSous.onPointerDown}
          className="af-hero-sous text-white/90 mt-3 max-w-md"
          style={{ fontSize: `${polices.subtitle}px`, textShadow: '0 2px 10px rgba(0,0,0,0.7)', ...peSous.style }}
        >
          {sousTitre}
        </p>
        {/* V544 : redit ce que dit le bouton — masquee sur telephone. */}
        <p
          ref={setRef('offre')}
          className="af-hero-offre mt-2 font-semibold text-white"
          style={{ textShadow: '0 2px 12px rgba(0,0,0,0.9)' }}
        >
          Ton premier cours est gratuit.
        </p>
        {/* Vrai <a> : si le JavaScript du clic echoue, la navigation se fait quand meme. */}
        <a
          ref={setRef('cta')}
          href={HREF_ESSAI}
          data-hero-el="cta"
          onPointerDown={peCta.onPointerDown}
          onClick={clicCta}
          draggable={modeEdition ? false : undefined}
          className={`mt-6 inline-flex items-center justify-center gap-2 font-bold rounded-full ${ctaLarge ? 'w-auto max-w-none' : 'w-full max-w-[260px]'}`}
          style={{
            pointerEvents: 'auto',
            background: 'var(--primary-color, #D91CD2)',
            color: '#fff',
            padding: '14px 26px',
            fontSize: `${polices.cta}px`,
            textDecoration: 'none',
            boxShadow: '0 6px 24px rgba(var(--primary-rgb, 217, 28, 210), 0.45)',
            ...peCta.style,
          }}
          data-testid="c1-hero-cta"
        >
          <SvgIcon name="headphones" size={18} />
          {libelleCta}
        </a>
      </div>
    );
  }

  // ═══════════════════ MODE POSITIONNE ═══════════════════
  const eff = {};
  HERO_ELEMENTS.forEach((el) => { eff[el] = elementEffectif(c.heroLayout, appareil, el); });
  const centre = (el) => (centres && centres[el]) || { x: eff[el].x, y: eff[el].y };
  // left/top a 0 + transform : la largeur disponible ne depend PAS de la
  // position (sinon le texte se re-couperait en bougeant -> mesure instable).
  const place = (el) => {
    const p = centre(el);
    return {
      position: 'absolute',
      left: 0,
      top: 0,
      transform: `translate(${(p.x * L).toFixed(2)}px, ${(p.y * H).toFixed(2)}px) translate(-50%, -50%)`,
    };
  };
  const sT = eff.title.size;
  const sS = eff.subtitle.size;
  const sC = eff.cta.size;
  const peTitre = pe('title');
  const peSous = pe('subtitle');
  const peCta = pe('cta');
  const ctaStyleMobile = {
    padding: `${13 * sC}px ${18 * sC}px`,
    fontSize: `${14 * sC}px`,
    lineHeight: 1.2,
    gap: 8 * sC,
    // < 768 : l'ancien `w-full` (330 max, ou toute la largeur moins px-6)
    minWidth: L < 768 ? Math.max(0, Math.min(330 * sC, L - 48)) : undefined,
  };
  const ctaStyleDesktop = {
    padding: `${14 * sC}px ${26 * sC}px`,
    fontSize: `${polices.cta * sC}px`,
    gap: 8 * sC,
  };

  return (
    <div
      ref={racineRef}
      data-hero-racine=""
      data-appareil={appareil}
      data-mode="positionne"
      className="absolute inset-0 af-hero-texte"
      style={{ pointerEvents: 'none', zIndex: 5, background: SCRIM, padding: 0 }}
    >
      <h1
        ref={setRef('title')}
        data-hero-el="title"
        onPointerDown={peTitre.onPointerDown}
        className="text-white font-extrabold"
        style={{
          ...place('title'),
          width: 'max-content',
          // min(90 % L, L - 48) : a 1 x, le titre se coupe EXACTEMENT comme en
          // mode flux (`px-6` = 24 px de chaque cote) -> aucun saut.
          maxWidth: Math.max(0, Math.min(0.9 * L, L - 48)),
          textAlign: eff.title.align,
          lineHeight: mobile ? 1.12 : 1.25,
          fontSize: `${polices.title * sT}px`,
          textShadow: '0 2px 14px rgba(0,0,0,0.75)',
          ...peTitre.style,
        }}
      >
        {titre}
      </h1>
      <p
        ref={setRef('subtitle')}
        data-hero-el="subtitle"
        onPointerDown={peSous.onPointerDown}
        className="af-hero-sous text-white/90"
        style={{
          ...place('subtitle'),
          width: 'max-content',
          maxWidth: Math.max(0, Math.min(448 * sS, 0.9 * L, L - 48)),
          textAlign: eff.subtitle.align,
          fontSize: `${polices.subtitle * sS}px`,
          textShadow: '0 2px 10px rgba(0,0,0,0.7)',
          ...peSous.style,
        }}
      >
        {sousTitre}
      </p>
      <div
        ref={setRef('cta')}
        data-hero-el="cta"
        onPointerDown={peCta.onPointerDown}
        className="flex flex-col items-center text-center"
        style={{ ...place('cta'), width: 'max-content', maxWidth: Math.max(0, L - 24), ...peCta.style }}
      >
        <p
          ref={setRef('offre')}
          className="af-hero-offre font-semibold text-white"
          style={{ fontSize: `${16 * sC}px`, lineHeight: 1.5, marginBottom: 24 * sC, textShadow: '0 2px 12px rgba(0,0,0,0.9)' }}
        >
          Ton premier cours est gratuit.
        </p>
        <a
          href={HREF_ESSAI}
          onClick={clicCta}
          draggable={modeEdition ? false : undefined}
          className="inline-flex items-center justify-center font-bold rounded-full"
          style={{
            pointerEvents: modeEdition ? 'none' : 'auto',
            background: 'var(--primary-color, #D91CD2)',
            color: '#fff',
            textDecoration: 'none',
            boxShadow: '0 6px 24px rgba(var(--primary-rgb, 217, 28, 210), 0.45)',
            maxWidth: '100%',
            ...(mobile ? ctaStyleMobile : ctaStyleDesktop),
          }}
          data-testid="c1-hero-cta"
        >
          <SvgIcon name="headphones" size={Math.round(18 * sC)} />
          {libelleCta}
        </a>
      </div>
    </div>
  );
}

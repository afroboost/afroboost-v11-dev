// V670 — Sélecteur de langue du site : UN composant, utilisé par PartnersCarousel (le
// sélecteur VISIBLE) et par App.js. Avant : deux listes recopiées à la main, des
// sigles sans nom (« BA », « CR », « LN » ne disent rien à personne), aucune langue
// active clairement marquée, aucune fermeture au clic extérieur, aucun clavier.
//
// Ce qu'il garantit :
//   - la liste vient de config/translateLangs.js — elle ne peut plus diverger ;
//   - chaque langue porte son NOM COMPLET (« Bàsàa (Bassa) », « Kreyòl ayisyen »),
//     le sigle n'est qu'un repère ;
//   - la langue ACTIVE se reconnaît à trois signes (coche, gras, fond), pas à la couleur seule ;
//   - une langue partielle ou à relire le DIT (« partiel » / « bêta ») au lieu de
//     laisser croire que tout est traduit ;
//   - fonctionne au doigt (cibles ≥ 44 px) et au clavier (↑ ↓ Début Fin Échap) ;
//   - ne déborde jamais de l'écran (largeur plafonnée, défilement interne).
//
// LE MENU EST RENDU DANS UN PORTAIL (document.body), en position FIXE.
//   Rendu à l'intérieur du bandeau, il était rogné ou recouvert : la barre d'onglets, plus bas
//   dans la page, interceptait le clic sur les dernières langues (Kreyòl) — mesuré dans un
//   navigateur. Un portail échappe à tous les contextes d'empilement et à tous les
//   `overflow: hidden` des ancêtres ; sa position vient du bouton, sa hauteur de la place
//   réellement disponible dans l'écran.
//
// Couleurs : toujours `var(--primary-color, …)` — le `#D91CD2` n'est qu'un repli
// (règle du projet : les couleurs du coach s'appliquent partout).
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { TRANSLATE_LANGS, STATUT_LANGUE } from '../config/translateLangs';
import { normaliserLangue } from '../utils/langue';
import { t as traduire } from '../utils/i18n';

const GlobeIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    <circle cx="12" cy="12" r="10" />
    <line x1="2" y1="12" x2="22" y2="12" />
    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
  </svg>
);

const CocheIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const PRIMAIRE_FOND = 'rgba(var(--primary-rgb, 217, 28, 210), 0.22)';

const LanguageMenu = ({ lang = 'fr', onChange, style }) => {
  const actif = normaliserLangue(lang);
  const langueActive = TRANSLATE_LANGS.find((l) => l.code === actif) || TRANSLATE_LANGS[0];
  const [ouvert, setOuvert] = useState(false);
  const racine = useRef(null);
  const bouton = useRef(null);
  const menu = useRef(null);
  const options = useRef([]);
  const [pos, setPos] = useState(null);

  const libelle = traduire('v_langue', actif);

  const fermer = useCallback((rendreLeFocus) => {
    setOuvert(false);
    if (rendreLeFocus && bouton.current) bouton.current.focus();
  }, []);

  // Position du menu d'après le bouton, et place réellement disponible sous lui.
  const calculerPosition = useCallback(() => {
    if (!bouton.current) return;
    const r = bouton.current.getBoundingClientRect();
    const marge = 12;
    const top = r.bottom + 8;
    const largeur = Math.min(232, window.innerWidth - 2 * marge);
    setPos({
      top,
      // Aligné sur le bord droit du bouton, mais JAMAIS hors de l'écran (bouton proche du bord gauche).
      left: Math.max(marge, Math.min(r.right - largeur, window.innerWidth - largeur - marge)),
      maxHeight: Math.max(160, window.innerHeight - top - marge),
    });
  }, []);

  useEffect(() => {
    if (!ouvert) { setPos(null); return undefined; }
    calculerPosition();
    // Le bouton bouge (défilement de la page, rotation de l'écran) : le menu se referme
    // plutôt que de rester flottant à un endroit qui n'a plus de sens.
    const fermerSurScroll = (e) => {
      if (menu.current && e.target && menu.current.contains(e.target)) return;   // défilement INTERNE du menu
      setOuvert(false);
    };
    window.addEventListener('resize', calculerPosition);
    window.addEventListener('scroll', fermerSurScroll, true);
    return () => {
      window.removeEventListener('resize', calculerPosition);
      window.removeEventListener('scroll', fermerSurScroll, true);
    };
  }, [ouvert, calculerPosition]);

  // Fermeture au clic / au toucher en dehors — le menu est dans un PORTAIL : on teste les deux.
  useEffect(() => {
    if (!ouvert) return undefined;
    const dehors = (e) => {
      const dansBouton = racine.current && racine.current.contains(e.target);
      const dansMenu = menu.current && menu.current.contains(e.target);
      if (!dansBouton && !dansMenu) setOuvert(false);
    };
    document.addEventListener('mousedown', dehors);
    document.addEventListener('touchstart', dehors);
    return () => {
      document.removeEventListener('mousedown', dehors);
      document.removeEventListener('touchstart', dehors);
    };
  }, [ouvert]);

  // À l'ouverture, le focus va sur la langue active (lecteur d'écran, clavier).
  useEffect(() => {
    if (!ouvert) return;
    const i = TRANSLATE_LANGS.findIndex((l) => l.code === actif);
    const el = options.current[i >= 0 ? i : 0];
    if (el && el.focus) el.focus();
  }, [ouvert, actif]);

  const choisir = (code) => {
    if (typeof onChange === 'function') onChange(code);
    fermer(true);
  };

  const clavier = (e) => {
    const n = TRANSLATE_LANGS.length;
    const courant = options.current.findIndex((el) => el === document.activeElement);
    let suivant = null;
    if (e.key === 'Escape') { e.preventDefault(); fermer(true); return; }
    if (e.key === 'ArrowDown') suivant = (courant + 1 + n) % n;
    else if (e.key === 'ArrowUp') suivant = (courant - 1 + n) % n;
    else if (e.key === 'Home') suivant = 0;
    else if (e.key === 'End') suivant = n - 1;
    if (suivant !== null) {
      e.preventDefault();
      if (options.current[suivant]) options.current[suivant].focus();
    }
  };

  return (
    <div ref={racine} className="relative" style={style}>
      <button
        ref={bouton}
        type="button"
        onClick={() => setOuvert((o) => !o)}
        className="w-7 h-7 flex items-center justify-center rounded-full transition-all hover:scale-110"
        style={{ background: 'rgba(255,255,255,0.1)', color: 'white', position: 'relative' }}
        aria-haspopup="listbox"
        aria-expanded={ouvert}
        aria-label={`${libelle} : ${langueActive.fullName}`}
        title={`${libelle} : ${langueActive.fullName}`}
        data-testid="lang-selector-btn"
      >
        <GlobeIcon />
        {/* Langue active, lisible sans ouvrir le menu. Sans effet sur la largeur du bouton. */}
        <span
          aria-hidden="true"
          data-testid="lang-active-badge"
          style={{
            position: 'absolute', right: '-5px', bottom: '-5px', minWidth: '16px', height: '14px',
            padding: '0 3px', borderRadius: '7px', background: PRIMAIRE, color: 'white',
            fontSize: '9px', fontWeight: 700, lineHeight: '14px', textAlign: 'center', letterSpacing: '0.2px',
          }}
        >
          {langueActive.label}
        </span>
      </button>

      {ouvert && pos && typeof document !== 'undefined' && createPortal(
        <div
          ref={menu}
          role="listbox"
          aria-label={libelle}
          onKeyDown={clavier}
          data-testid="lang-menu"
          className="py-1 rounded-xl"
          style={{
            position: 'fixed',
            top: pos.top,
            left: pos.left,
            background: 'rgba(0,0,0,0.96)',
            border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.4)',
            boxShadow: '0 12px 32px rgba(0,0,0,0.55)',
            width: '232px',
            maxWidth: 'calc(100vw - 24px)',
            maxHeight: pos.maxHeight,
            overflowY: 'auto',
            zIndex: 10050,                           // au-dessus du chat, des barres et des fenêtres
          }}
        >
          {TRANSLATE_LANGS.map((l, i) => {
            const estActive = l.code === actif;
            const statut = STATUT_LANGUE[l.status] || STATUT_LANGUE.complete;
            return (
              <button
                key={l.code}
                ref={(el) => { options.current[i] = el; }}
                type="button"
                role="option"
                aria-selected={estActive}
                aria-label={statut.aide ? `${l.fullName} — ${statut.aide}` : l.fullName}
                onClick={() => choisir(l.code)}
                data-testid={`lang-${l.code}`}
                className="w-full flex items-center gap-3 px-3 text-left text-white hover:bg-white/10 focus:bg-white/10 outline-none"
                style={{
                  minHeight: '44px',                       // cible tactile
                  background: estActive ? PRIMAIRE_FOND : 'transparent',
                  fontWeight: estActive ? 700 : 400,
                }}
              >
                <span
                  aria-hidden="true"
                  style={{
                    flex: '0 0 auto', width: '28px', textAlign: 'center', fontSize: '11px',
                    fontWeight: 700, opacity: 0.8,
                    color: estActive ? PRIMAIRE : 'inherit',
                  }}
                >
                  {l.label}
                </span>
                <span style={{ flex: '1 1 auto', minWidth: 0, fontSize: '14px', lineHeight: 1.2 }}>
                  {l.fullName}
                  {statut.etiquette && (
                    <span
                      title={statut.aide}
                      style={{
                        marginLeft: '8px', padding: '1px 6px', borderRadius: '8px', fontSize: '10px',
                        fontWeight: 500, border: '1px solid rgba(255,255,255,0.35)', opacity: 0.85,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {statut.etiquette}
                    </span>
                  )}
                </span>
                <span aria-hidden="true" style={{ flex: '0 0 auto', width: '16px', color: PRIMAIRE }}>
                  {estActive ? <CocheIcon /> : null}
                </span>
              </button>
            );
          })}
        </div>,
        document.body,
      )}
    </div>
  );
};

export default LanguageMenu;

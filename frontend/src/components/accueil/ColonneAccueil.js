/**
 * V540 — LA COLONNE DE LA PAGE D'ACCUEIL : Live · Offre du moment · Spordateur.
 *
 * CE QUE CE FICHIER N'EST PAS : un nouveau moteur. Il ne connaît ni les règles
 * commerciales, ni l'état du direct, ni la façon d'entrer dans Spordateur. Il
 * REÇOIT tout d'App.js, qui garde ses handlers existants — `ouvrirLiveDepuisLaBarre`,
 * `handleSelectOffer`, `entrerDansSpordate`. Trois cartes, zéro logique métier.
 *
 * POURQUOI CES TROIS-LÀ, ET DANS CET ORDRE. L'audit a montré que le signal le
 * plus fort de la plateforme — « le coach est en direct » — tenait dans une
 * pastille de 31 px coincée dans le menu, entre « Shop » et « Spordateur ».
 * Il passe en tête de colonne. Les offres, elles, occupaient trois grandes
 * cartes en pleine largeur au milieu du contenu : il n'en reste qu'une ici, et
 * le catalogue entier reste accessible par « Voir toutes les offres », qui est
 * le mécanisme existant. Spordateur ferme la marche, volontairement plus petit
 * que le Live : c'est un univers complémentaire, pas le cœur d'Afroboost.
 */
import React from 'react';
import SvgIcon from '../SvgIcon';

const CADRE = {
  border: '1px solid rgba(255,255,255,0.12)',
  borderRadius: 14,
  background: 'rgba(255,255,255,0.03)',
  overflow: 'hidden',
};
const BOUTON = {
  minHeight: 44, width: '100%', marginTop: 13,
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
  borderRadius: 999, border: '1px solid rgba(255,255,255,0.12)',
  background: 'rgba(255,255,255,0.06)', color: '#fff',
  fontSize: 14, fontWeight: 600, cursor: 'pointer', padding: '0 16px',
};
const BOUTON_PLEIN = {
  ...BOUTON,
  background: 'var(--primary-color, #D91CD2)',
  borderColor: 'transparent',
  fontWeight: 700,
};
/* `body` porte `color: rgb(10,10,10)` dans cette application : tout texte qui
   HÉRITE devient noir sur noir. Le reste du site s'en sort avec `text-white`
   posé classe par classe. On pose donc la couleur explicitement, ici aussi. */
const TITRE = { margin: 0, fontSize: 17, fontWeight: 700, letterSpacing: '-0.01em', color: '#fff' };
const SOUS = { color: 'rgba(255,255,255,0.6)', fontSize: 13.5, lineHeight: 1.45, margin: '5px 0 0' };

/**
 * AFROBOOST LIVE — deux états, une seule source : `live-status`, que la barre
 * de navigation lisait déjà. La carte existe même hors direct, parce que le
 * Live fait partie de l'écosystème et méritait mieux qu'une pastille.
 *
 * Les trois barres ne bougent QUE pendant un direct : c'est le seul mouvement
 * non déclenché de la page, et il veut dire quelque chose — il y a du son en ce
 * moment. Coupé si le système demande moins d'animations.
 */
export const CarteLive = ({ enDirect, onOuvrir, occupe, titreHors, titreEnCours }) => (
  <div
    style={enDirect
      ? { ...CADRE, borderColor: 'rgba(255,59,48,0.5)', background: 'linear-gradient(140deg, rgba(255,59,48,0.16), rgba(var(--primary-rgb, 217, 28, 210), 0.10) 58%, rgba(255,255,255,0.02))' }
      : CADRE}
    data-testid="accueil-carte-live"
    data-live-en-cours={enDirect ? 'true' : 'false'}
  >
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
        {enDirect ? (
          <span className="af-live-barres" aria-hidden="true" style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 22, flex: '0 0 auto' }}>
            <i /><i /><i />
          </span>
        ) : (
          <span
            aria-hidden="true"
            style={{
              width: 38, height: 38, borderRadius: '50%', flex: '0 0 auto',
              border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.45)',
              background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.14)',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--primary-color, #D91CD2)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="m23 7-7 5 7 5z" /><rect x="1" y="5" width="15" height="14" rx="2" />
            </svg>
          </span>
        )}
        <div style={{ minWidth: 0 }}>
          {enDirect && (
            <div style={{ fontSize: 11, letterSpacing: '.07em', color: '#ff8a82', fontWeight: 700 }}>EN DIRECT</div>
          )}
          <h3 style={TITRE}>Afroboost Live</h3>
          {!enDirect && <p style={SOUS}>{titreHors}</p>}
        </div>
      </div>
      <button
        type="button"
        onClick={onOuvrir}
        disabled={occupe}
        data-testid="accueil-live-ouvrir"
        style={enDirect ? BOUTON_PLEIN : BOUTON}
      >
        {occupe ? '…' : (enDirect ? titreEnCours : 'Découvrir le Live')}
      </button>
    </div>
  </div>
);

/**
 * L'OFFRE DU MOMENT — UNE carte, pas trois.
 *
 * L'offre montrée est celle que le coach a lui-même marquée comme urgente (un
 * compte à rebours) ; à défaut, la première offre de service publique. Le
 * choix n'est donc pas un classement inventé ici : il relit un réglage qui
 * existe déjà dans l'offre.
 *
 * `onChoisir` est `handleSelectOffer` d'App.js — le MÊME point d'entrée que
 * partout ailleurs. Rien n'est recréé : ni fiche, ni checkout, ni compte à
 * rebours (`Countdown` est le composant existant).
 */
export const CarteOffreDuMoment = ({ offre, badge, prix, unite, detail, media, Countdown, onChoisir, onToutesLesOffres, nbOffres }) => {
  if (!offre) return null;
  return (
    <div style={CADRE} data-testid="accueil-offre-du-moment">
      {media ? (
        <div style={{ aspectRatio: '16 / 9', background: '#0c0c0e' }}>
          <img src={media} alt="" loading="lazy" decoding="async" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        </div>
      ) : null}
      <div style={{ padding: 16 }}>
        {badge ? (
          <span style={{
            display: 'inline-block', padding: '4px 9px', borderRadius: 999, marginBottom: 8,
            background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.18)',
            border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.45)',
            fontSize: 10.5, letterSpacing: '.06em', fontWeight: 700,
          }}>{badge}</span>
        ) : null}
        <h3 style={TITRE}>{(offre.name || '').trim()}</h3>
        <p style={{ display: 'flex', alignItems: 'baseline', gap: 6, margin: '8px 0 0' }}>
          <b style={{ fontSize: 26, fontWeight: 800, color: 'var(--primary-color, #D91CD2)', letterSpacing: '-0.02em' }}>{prix}</b>
          {unite ? <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.6)' }}>{unite}</span> : null}
        </p>
        {detail ? <p style={SOUS}>{detail}</p> : null}
        {Countdown ? <Countdown offer={offre} /> : null}
        <button
          type="button"
          onClick={() => onChoisir(offre)}
          data-testid="accueil-offre-cta"
          style={BOUTON_PLEIN}
        >
          Voir l’offre
        </button>
        <button
          type="button"
          onClick={onToutesLesOffres}
          data-testid="accueil-toutes-offres"
          style={{
            display: 'block', width: '100%', marginTop: 10, minHeight: 44,
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'rgba(255,255,255,0.8)', fontSize: 13.5, fontWeight: 600,
            textDecoration: 'underline', textUnderlineOffset: 3,
          }}
        >
          Voir toutes les offres{nbOffres ? ` (${nbOffres})` : ''}
        </button>
      </div>
    </div>
  );
};

/**
 * SPORDATEUR — volontairement la plus petite carte de la page.
 *
 * Elle quitte le menu principal sans rien perdre : `href` et `onClick` sont
 * ceux qu'App.js utilisait déjà (route serveur `/api/spordate/enter` pour le
 * clic milieu et la navigation sans JS, `entrerDansSpordate` au clic gauche,
 * préchargement au survol). Aucun accès n'est retiré, il change de place.
 */
export const CarteSpordateur = ({ href, onClick, onPrecharger }) => (
  <div style={{ ...CADRE, background: 'rgba(255,255,255,0.02)' }} data-testid="accueil-carte-spordateur">
    <div className="af-carte-spordateur" style={{ padding: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
      <span
        aria-hidden="true"
        style={{
          width: 38, height: 38, borderRadius: '50%', flex: '0 0 auto',
          border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.45)',
          background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.14)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        <SvgIcon name="users" size={18} />
      </span>
      <div style={{ minWidth: 0 }}>
        <h3 style={TITRE}>Spordateur</h3>
        <p style={SOUS}>Trouver un partenaire de sport.</p>
      </div>
      <a
        href={href}
        onClick={onClick}
        onMouseEnter={onPrecharger}
        onFocus={onPrecharger}
        onTouchStart={onPrecharger}
        data-testid="accueil-spordateur-ouvrir"
        style={{ ...BOUTON, width: 'auto', marginTop: 0, marginLeft: 'auto', minHeight: 40, fontSize: 13, textDecoration: 'none', flex: '0 0 auto' }}
      >
        Découvrir
      </a>
    </div>
  </div>
);

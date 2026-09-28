/**
 * V554 — LA BARRE HAUTE : compte à rebours + « Retour au dashboard », UNE barre.
 *
 * AVANT. Deux éléments `position: fixed` qui s'ignoraient :
 *   - le bandeau du compte à rebours (z-index 40, 50 px desktop / 64 px mobile) ;
 *   - le bouton « Retour au dashboard » de la Vue visiteur (top 16, right 16,
 *     z-index 9999), posé PAR-DESSUS le bandeau ET par-dessus le globe de
 *     langue du carrousel.
 *   Et la page ne réservait que 56 px (desktop) ou 2 px (mobile, règle V146
 *   `.section-gradient { padding: 2px !important }`) : le logo « Afroboost »
 *   et le globe passaient SOUS le bandeau.
 *
 * APRÈS. Une grille à zones réservées, sans aucune surenchère de z-index :
 *   desktop  [ Retour ] [ Compte à rebours ] [ zone droite vide ]
 *   < 1024   [ Retour ] [ Compte à rebours sur 2 lignes      ]
 * La barre publie SA hauteur mesurée dans `--af-bandeau` ; la page réserve
 * exactement cette hauteur (App.css, `.af-barre-haute-page`) et la barre de
 * navigation sticky s'y accroche déjà (V541). Plus rien ne passe dessous.
 * Rien à afficher -> `null`, et `--af-bandeau` revient à 0 px.
 *
 * Couleurs : uniquement var(--primary-color) / --primary-rgb (règle absolue).
 * Icône : SVG inline stroke="currentColor" (l'ancien bandeau utilisait des emoji).
 */
import React, { useLayoutEffect, useRef } from 'react';
import { etatBarreHaute } from '../../utils/barreHaute';

function IconeFlamme() {
  return (
    <svg className="af-barre-haute-icone" width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z" />
    </svg>
  );
}

function IconeRetour() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M19 12H5" />
      <path d="M12 19l-7-7 7-7" />
    </svg>
  );
}

/**
 * props :
 *  - compte        : null | { texte, minuteur, slogan }
 *  - modeVisiteur  : bool
 *  - libelleRetour : texte complet (« Retour au dashboard »), aussi aria-label
 *  - libelleCourt  : texte mobile (« Dashboard »)
 *  - onRetour      : () => void
 */
export default function BarreHaute(props) {
  var etat = etatBarreHaute({ compteActif: !!props.compte, modeVisiteur: !!props.modeVisiteur });
  var ref = useRef(null);

  // La hauteur RÉELLE (le compte à rebours peut passer sur deux lignes, une
  // traduction peut être plus longue) : mesurée, jamais devinée. Dépend d'une
  // primitive (`etat.disposition`), pas d'un objet : aucune boucle possible.
  useLayoutEffect(function() {
    var racine = document.documentElement;
    var el = ref.current;
    if (!el) { racine.style.setProperty('--af-bandeau', '0px'); return undefined; }
    var mesurer = function() {
      var h = Math.ceil(el.getBoundingClientRect().height) + 'px';
      if (racine.style.getPropertyValue('--af-bandeau') !== h) racine.style.setProperty('--af-bandeau', h);
    };
    mesurer();
    var obs = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(mesurer) : null;
    if (obs) obs.observe(el);
    window.addEventListener('resize', mesurer);
    return function() {
      window.removeEventListener('resize', mesurer);
      if (obs) obs.disconnect();
      racine.style.setProperty('--af-bandeau', '0px');
    };
  }, [etat.disposition]);

  if (!etat.visible) return null;

  var c = props.compte;
  return (
    <div
      ref={ref}
      className={'af-barre-haute af-barre-haute--' + etat.disposition}
      data-af-barre-haute="1"
      data-sticky-countdown={etat.compte ? 'active' : undefined}
      role="region"
      aria-label={etat.compte ? c.texte : props.libelleRetour}
    >
      {etat.retour && (
        <button
          type="button"
          className="af-barre-haute-retour"
          data-testid="af-barre-haute-retour"
          aria-label={props.libelleRetour}
          title={props.libelleRetour}
          onClick={props.onRetour}
        >
          <IconeRetour />
          <span className="af-barre-haute-retour-long">{props.libelleRetour}</span>
          <span className="af-barre-haute-retour-court">{props.libelleCourt || props.libelleRetour}</span>
        </button>
      )}
      {etat.compte && (
        <div className="af-barre-haute-compte" data-testid="af-barre-haute-compte">
          <span className="af-barre-haute-libelle">
            <IconeFlamme />
            <span className="af-barre-haute-texte">{c.texte}</span>
            <span className="af-barre-haute-deuxpoints"> :</span>
          </span>
          <span className="af-barre-haute-minuteur" aria-live="off">{c.minuteur}</span>
          {c.slogan && <span className="af-barre-haute-slogan">{'— ' + c.slogan}</span>}
        </div>
      )}
      {etat.compte && etat.retour && <span className="af-barre-haute-droite" aria-hidden="true" />}
    </div>
  );
}

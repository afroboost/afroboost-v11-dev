/**
 * PAR-3 — PAGE /duo/c/<token> : l'entrée d'une invitation de campagne.
 *
 * Le visiteur ouvre le lien d'un coach. Cette page ne montre qu'un écran
 * d'attente : elle obtient (ou retrouve) SON invitation racine, puis ouvre
 * /duo/<share_token> par `location.replace` (pas d'entrée d'historique).
 *
 *   - entrée déjà connue sur l'appareil → redirection directe, AUCUN appel ;
 *   - sinon UN SEUL POST (garde `useRef`, jamais rejoué au re-rendu) ;
 *   - refus → message clair ; erreur réseau → bouton « Réessayer » (geste).
 *
 * Couleurs : classes `cp-` (variables du coach uniquement). noindex : /duo.
 */
import React, { useEffect, useRef, useState } from 'react';
import SvgIcon from '../SvgIcon';
import {
  lireEntreeCampagne, entrerCampagne, cibleInvitation, messageEntreeCampagne, navigation,
} from '../../utils/parrainageCampagne';
import './parrainage.css';

function Cadre({ children }) {
  return (
    <div className="cp-root cp-page" data-testid="entree-campagne">
      <main className="cp-app">
        <header className="cp-header">
          <a className="cp-logo" href="/" aria-label="Afroboost">Afro<span>boost</span></a>
          <div className="cp-pill">Invitation</div>
        </header>
        {children}
        <footer className="cp-footer">Danse · Fitness · Good vibes</footer>
      </main>
    </div>
  );
}

export default function EntreeCampagne({ token }) {
  const [etat, setEtat] = useState('attente'); // attente | message | reseau
  const [message, setMessage] = useState('');
  const lance = useRef('');

  const entrer = () => {
    setEtat('attente');
    entrerCampagne(token).then(
      (r) => { navigation.remplacer(r.target); },
      (refus) => {
        const m = messageEntreeCampagne(refus);
        if (m) { setMessage(m); setEtat('message'); } else setEtat('reseau');
      },
    );
  };

  useEffect(() => {
    if (!token || lance.current === token) return;
    lance.current = token;
    const connue = lireEntreeCampagne(token);
    if (connue && connue.share_token) { navigation.remplacer(cibleInvitation(connue.share_token)); return; }
    entrer();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  if (etat === 'message') {
    return (
      <Cadre>
        <div className="cp-state">
          <div className="cp-roundic"><SvgIcon name="warning" size={38} /></div>
          <h1 className="cp-h1 cp-center" data-testid="entree-campagne-message">{message}</h1>
          <a className="cp-b cp-b--ghost" href="/" data-testid="entree-campagne-accueil">Découvrir Afroboost</a>
        </div>
      </Cadre>
    );
  }
  if (etat === 'reseau') {
    return (
      <Cadre>
        <div className="cp-state">
          <div className="cp-roundic"><SvgIcon name="warning" size={38} /></div>
          <h1 className="cp-h1 cp-center" data-testid="entree-campagne-message">Connexion impossible pour le moment.</h1>
          <p className="cp-lead cp-center">Vérifie ta connexion puis réessaie.</p>
          <button type="button" className="cp-b" onClick={entrer} data-testid="entree-campagne-reessayer">
            <SvgIcon name="refresh" size={20} /> Réessayer
          </button>
        </div>
      </Cadre>
    );
  }
  return (
    <Cadre>
      <div className="cp-state" data-testid="entree-campagne-attente">
        <div className="cp-spinner" aria-hidden="true" />
        <p className="cp-lead">On prépare ton invitation…</p>
      </div>
    </Cadre>
  );
}

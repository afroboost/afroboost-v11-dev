/**
 * V610b — « Tu as un abonnement 8 mois actif ? » : MÊME bloc pour TOUT LE MONDE.
 *
 * CONFIDENTIALITÉ : ce bloc ne dépend d'AUCUNE donnée de la personne. Il n'interroge
 * jamais le statut membre d'un e-mail saisi (une adresse ne prouve pas l'identité).
 * La gratuité ne s'obtient QUE dans l'espace membre, après authentification (code
 * e-mail) : c'est le serveur qui la vérifie, pour la personne connectée seulement.
 *
 * « Accéder à mon espace membre » : session déjà ouverte sur cet appareil -> l'espace ;
 * sinon, le parcours d'accès EXISTANT (lien envoyé par e-mail, POST /subscriber/recover)
 * avec un message IDENTIQUE quoi qu'il arrive — l'écran ne dit jamais si l'adresse
 * correspond à un compte.
 */
import React, { useState } from 'react';
import SvgIcon from './SvgIcon';
import { lireSession, urlDeLaSession } from '../utils/espaceSession';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;
export const TEXTE_NEUTRE = "Si cette adresse correspond à un espace membre, un lien d'accès vient d'y être envoyé.";
const RE_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export default function AccesMembreEvenement({ libelle = 'Accéder à mon espace membre', compact = false, inerte = false, avantOuverture = null }) {
  const [formulaire, setFormulaire] = useState(false);
  const [email, setEmail] = useState('');
  const [etat, setEtat] = useState('');        // '' | 'envoi' | 'fait' | 'erreur:<texte>'

  const ouvrir = () => {
    if (inerte) return;                          // V610e : aperçu de l'éditeur coach
    // V610m : l'événement visé est retenu — l'espace s'ouvrira sur CET événement.
    if (typeof avantOuverture === 'function') { try { avantOuverture(); } catch (e) { /* ignore */ } }
    const cible = urlDeLaSession(lireSession());
    if (cible) { window.location.href = cible; return; }
    setFormulaire(true);
  };

  const envoyer = async (e) => {
    e.preventDefault();
    const adresse = String(email || '').trim().toLowerCase();
    if (!RE_EMAIL.test(adresse)) { setEtat('erreur:Adresse e-mail invalide.'); return; }
    setEtat('envoi');
    try {
      const r = await fetch(`${BACKEND_URL}/api/subscriber/recover`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: adresse }) });
      // 200 et 404 (aucun accès) s'affichent PAREIL : l'écran ne révèle rien.
      if (r.status === 429) setEtat('erreur:Trop de tentatives. Réessaie dans quelques minutes.');
      else if (r.status < 500) setEtat('fait');
      else setEtat('erreur:Envoi impossible pour le moment. Réessaie.');
    } catch (err) {
      setEtat('erreur:Envoi impossible pour le moment. Réessaie.');
    }
  };

  return (
    <div data-testid="acces-membre-evenement" style={{ marginTop: compact ? 10 : 14, padding: compact ? '10px 12px' : '14px',
      borderRadius: 14, background: rgbaP(0.08), border: `1px solid ${rgbaP(0.3)}`, textAlign: 'left' }}>
      <p style={{ margin: 0, display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 14, fontWeight: 700, color: 'rgba(255,255,255,0.95)' }}>
        <span style={{ color: PRIMAIRE, display: 'inline-flex', marginTop: 1 }}><SvgIcon name="heart" size={16} /></span>
        <span>Tu as un abonnement Afroboost 8 mois actif ?</span>
      </p>
      <p style={{ margin: '4px 0 10px 24px', fontSize: 13.5, color: 'rgba(255,255,255,0.8)' }}>
        Ta place est offerte. Réserve-la depuis ton espace membre.
      </p>
      {!formulaire ? (
        <button type="button" data-testid="acces-membre-bouton" onClick={ouvrir}
                style={{ width: '100%', minHeight: 44, borderRadius: 12, background: 'rgba(255,255,255,0.06)',
                  border: `1px solid ${rgbaP(0.45)}`, color: 'rgba(255,255,255,0.95)', fontWeight: 700, fontSize: 14, cursor: 'pointer' }}>
          {libelle}
        </button>
      ) : etat === 'fait' ? (
        <p data-testid="acces-membre-neutre" role="status" style={{ margin: 0, fontSize: 13.5, color: 'rgba(255,255,255,0.9)' }}>{TEXTE_NEUTRE}</p>
      ) : (
        <form onSubmit={envoyer} noValidate>
          <input type="email" data-testid="acces-membre-email" value={email} placeholder="Ton adresse e-mail de membre"
                 onChange={(e) => { setEmail(e.target.value); if (etat) setEtat(''); }} autoComplete="email" inputMode="email"
                 style={{ width: '100%', minHeight: 44, borderRadius: 10, padding: '0 12px', boxSizing: 'border-box',
                   background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.18)', color: 'rgba(255,255,255,0.95)' }} />
          <button type="submit" data-testid="acces-membre-envoyer" disabled={etat === 'envoi'}
                  style={{ width: '100%', minHeight: 44, marginTop: 8, borderRadius: 12, border: 'none', background: PRIMAIRE,
                    color: 'rgba(255,255,255,1)', fontWeight: 700, fontSize: 14, cursor: 'pointer', opacity: etat === 'envoi' ? 0.7 : 1 }}>
            {etat === 'envoi' ? 'Envoi…' : "Recevoir mon lien d'accès"}
          </button>
          {etat.startsWith('erreur:') ? (
            <p role="alert" style={{ margin: '6px 0 0', fontSize: 13, color: 'rgba(255,170,170,1)' }}>{etat.slice(7)}</p>
          ) : null}
        </form>
      )}
    </div>
  );
}

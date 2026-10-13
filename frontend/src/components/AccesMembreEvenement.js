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

export default function AccesMembreEvenement({ libelle = 'Accéder à mon espace membre', compact = false, inerte = false, avantOuverture = null,
  offreVisee = '', jetonInvitation = '' }) {
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
    if (typeof avantOuverture === 'function') { try { avantOuverture(); } catch (x) { /* ignore */ } }   // V610p
    setEtat('envoi');
    try {
      const r = await fetch(`${BACKEND_URL}/api/subscriber/recover`, {
        // V610p : l'événement d'où vient la demande voyage jusqu'au lien de l'e-mail (vérifié
        // par le serveur) -> le lien rouvre l'espace sur CET événement, même dans un autre navigateur.
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({ email: adresse }, offreVisee && jetonInvitation ? { offre: offreVisee, jeton: jetonInvitation } : {})) });
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
        <span>Déjà membre Afroboost ?</span>
      </p>
      <p style={{ margin: '4px 0 10px 24px', fontSize: 13.5, color: 'rgba(255,255,255,0.8)' }}>
        {/* V618M : l'avantage (gratuit, réduction, prix membre) est réglé par le coach, offre par offre. */}
        Ton abonnement peut te donner droit à un tarif spécial. Découvre-le dans ton espace membre.
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

/**
 * V618L — LE PARCOURS MEMBRE DE LA PAGE ÉVÉNEMENT, en une étape :
 *   « Entre l'adresse e-mail liée à ton abonnement Afroboost. » [e-mail] [RECEVOIR MON LIEN D'ACCÈS]
 *   -> « Lien d'accès envoyé » + [RENVOYER LE LIEN] [CHANGER D'ADRESSE].
 * Le lien de l'e-mail porte l'ÉVÉNEMENT (offre + jeton d'invitation, vérifiés par le serveur) :
 * il ouvre l'espace directement sur « Ta place est offerte avec ton abonnement ».
 * Même écran pour toute adresse (V389 / V591) : la page ne dit jamais qui est membre. Aucun
 * bouton « Ouvrir Gmail » : rien ne garantit que l'adresse soit chez Gmail, ni l'appli installée.
 */
export function DemandeLienMembre({ inerte = false, avantEnvoi = null, offreVisee = '', jetonInvitation = '' }) {
  const [email, setEmail] = useState('');
  const [etat, setEtat] = useState('');        // '' | 'envoi' | 'fait' | 'renvoye' | 'erreur:<texte>'
  const [dejaEnvoye, setDejaEnvoye] = useState(false);   // un envoi a réussi : l'écran « envoyé » reste
  const envoyer = async (e) => {
    if (e && e.preventDefault) e.preventDefault();
    if (inerte || etat === 'envoi') return;
    const adresse = String(email || '').trim().toLowerCase();
    if (!RE_EMAIL.test(adresse)) { setEtat('erreur:Adresse e-mail invalide.'); return; }
    if (typeof avantEnvoi === 'function') { try { avantEnvoi(); } catch (x) { /* ignore */ } }
    const deja = dejaEnvoye;
    setEtat('envoi');
    try {
      const r = await fetch(`${BACKEND_URL}/api/subscriber/recover`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({ email: adresse }, offreVisee && jetonInvitation ? { offre: offreVisee, jeton: jetonInvitation } : {})) });
      if (r.status === 429) setEtat('erreur:Trop de demandes. Attends quelques minutes avant de redemander un lien.');
      else if (r.status < 500) { setDejaEnvoye(true); setEtat(deja ? 'renvoye' : 'fait'); }
      else setEtat('erreur:Envoi impossible pour le moment. Réessaie.');
    } catch (err) {
      setEtat('erreur:Envoi impossible pour le moment. Réessaie.');
    }
  };
  // Après un premier envoi réussi, l'écran « envoyé » reste (une erreur de RENVOI s'y affiche).
  const envoye = dejaEnvoye;
  const bouton = (plein) => ({ width: '100%', minHeight: 46, borderRadius: 12, fontWeight: 800, fontSize: 14.5, cursor: 'pointer',
    border: plein ? 'none' : `1px solid ${rgbaP(0.45)}`, background: plein ? PRIMAIRE : 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,1)' });
  return (
    <div data-testid="membre-lien" style={{ margin: '4px 0 14px', padding: 14, borderRadius: 14, background: rgbaP(0.08), border: `1px solid ${rgbaP(0.3)}`, textAlign: 'left' }}>
      {envoye ? (
        <div data-testid="membre-lien-envoye" role="status">
          <p style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8, fontWeight: 800, fontSize: 16, color: 'rgba(255,255,255,0.97)' }}>
            <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="check" size={20} /></span> Lien d'accès envoyé
          </p>
          <p style={{ margin: '6px 0 12px', fontSize: 14, color: 'rgba(255,255,255,0.85)', lineHeight: 1.45 }}>
            Ouvre l'e-mail Afroboost que nous venons de t'envoyer et touche « Accéder à mon espace ».
          </p>
          {/* V618N : l'adresse TAPÉE (jamais une donnée du serveur) — une erreur d'adresse se voit tout de suite. */}
          <p data-testid="membre-lien-adresse" style={{ margin: '-6px 0 12px', fontSize: 13, color: 'rgba(255,255,255,0.7)', wordBreak: 'break-all' }}>
            Adresse utilisée : <strong style={{ color: 'rgba(255,255,255,0.95)' }}>{String(email || '').trim().toLowerCase()}</strong>
          </p>
          {etat.startsWith('erreur:') ? <p role="alert" data-testid="membre-lien-erreur" style={{ margin: '0 0 10px', fontSize: 13, color: 'rgba(255,170,170,1)' }}>{etat.slice(7)}</p> : null}
          {etat === 'renvoye' ? <p data-testid="membre-lien-renvoye" style={{ margin: '0 0 10px', fontSize: 13, color: 'rgba(255,255,255,0.7)' }}>Un nouveau lien est parti. Pense à regarder tes courriers indésirables.</p> : null}
          <div style={{ display: 'grid', gap: 8 }}>
            <button type="button" data-testid="membre-lien-renvoyer" onClick={envoyer} disabled={etat === 'envoi'} style={bouton(false)}>{etat === 'envoi' ? 'Envoi…' : 'Renvoyer le lien'}</button>
            <button type="button" data-testid="membre-lien-changer" onClick={() => { setDejaEnvoye(false); setEtat(''); }} style={bouton(false)}>Changer d'adresse</button>
          </div>
        </div>
      ) : (
        <form onSubmit={envoyer} noValidate>
          <p style={{ margin: '0 0 10px', fontSize: 14, color: 'rgba(255,255,255,0.9)' }}>Entre l'adresse e-mail liée à ton abonnement Afroboost.</p>
          <input type="email" data-testid="membre-lien-email" value={email} placeholder="ton.adresse@exemple.ch"
                 onChange={(e) => { setEmail(e.target.value); if (etat.startsWith('erreur:')) setEtat(''); }} autoComplete="email" inputMode="email"
                 style={{ width: '100%', minHeight: 46, borderRadius: 10, padding: '0 12px', boxSizing: 'border-box', fontSize: 16,
                   background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.18)', color: 'rgba(255,255,255,0.95)' }} />
          <button type="submit" data-testid="membre-lien-envoyer" disabled={etat === 'envoi'} style={Object.assign(bouton(true), { marginTop: 8, opacity: etat === 'envoi' ? 0.7 : 1 })}>
            {etat === 'envoi' ? 'Envoi…' : "Recevoir mon lien d'accès"}
          </button>
          {etat.startsWith('erreur:') ? <p role="alert" style={{ margin: '6px 0 0', fontSize: 13, color: 'rgba(255,170,170,1)' }}>{etat.slice(7)}</p> : null}
        </form>
      )}
    </div>
  );
}

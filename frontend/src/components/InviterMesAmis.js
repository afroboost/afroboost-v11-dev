/**
 * V607 — « INVITE TES AMIS » APRÈS UN ÉVÉNEMENT (facultatif, jamais bloquant).
 *
 * Affiché dans la confirmation de paiement (événement payant) ou d'inscription
 * (événement gratuit), SEULEMENT si la personne est arrivée par une invitation
 * (`af_invitation`, posé par `?inv=`). Le serveur lui donne SON lien personnel
 * (`/i/<jeton>`, génération suivante) : par la session Stripe payée, ou par sa
 * réservation récente. Sans invitation, ou si le serveur ne répond pas : RIEN
 * n'est affiché (aucune autre confirmation n'est modifiée).
 *
 * Honnêteté : le clic WhatsApp OUVRE WhatsApp avec le message prérempli ; on
 * enregistre « partage déclenché », jamais « envoyé ». Aucun envoi automatique.
 */
import React, { useEffect, useState } from 'react';
import SvgIcon from './SvgIcon';
import { invitationActuelle } from '../utils/attribution';
import { suivreInvitation } from '../utils/invitationSuivi';
import { texteWhatsAppCampagne } from '../utils/invitationCampagne';
import { lienWhatsApp, copier } from '../utils/parrainage';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;
const ESSAIS = 6;

function attendre(ms) { return new Promise((r) => setTimeout(r, ms)); }

/** Le lien personnel : par la session Stripe (le webhook peut avoir un peu de retard). */
async function lienParSession(sessionId) {
  for (let i = 0; i < ESSAIS; i += 1) {
    try {
      const r = await fetch(`${BACKEND_URL}/api/invitation/relais/session/${encodeURIComponent(sessionId)}`);
      if (r.ok) return r.json();
    } catch (e) { /* réseau : on retente */ }
    await attendre(1500 + i * 500);
  }
  return null;
}

async function lienParInscription(jeton, code) {
  try {
    const r = await fetch(`${BACKEND_URL}/api/invitation/relais/inscription`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jeton, code }),
    });
    return r.ok ? r.json() : null;
  } catch (e) { return null; }
}

async function lienParReservation(jeton, code) {
  try {
    const r = await fetch(`${BACKEND_URL}/api/invitation/relais/reservation`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jeton, reservation_code: code }),
    });
    return r.ok ? r.json() : null;
  } catch (e) { return null; }
}

export default function InviterMesAmis({ sessionId, reservationCode, codeAcces }) {
  const [relais, setRelais] = useState(null);
  const [details, setDetails] = useState(null);
  const [retour, setRetour] = useState('');
  const inv = invitationActuelle();
  const jetonInv = inv ? inv.t : '';
  const cs = /^cs_[A-Za-z0-9_]+$/.test(String(sessionId || '')) ? String(sessionId) : '';
  const code = String(reservationCode || '');
  const acces = /^[A-Za-z0-9-]{4,40}$/.test(String(codeAcces || '')) ? String(codeAcces) : '';

  useEffect(() => {
    if (!jetonInv || (!cs && !code && !acces)) return undefined;
    let vivant = true;
    const demande = cs ? lienParSession(cs) : (code ? lienParReservation(jetonInv, code) : lienParInscription(jetonInv, acces));
    demande.then((r) => {
      if (!vivant || !r || !r.jeton) return;
      setRelais(r);
      fetch(`${BACKEND_URL}/api/invitation/publique/${encodeURIComponent(r.jeton)}`)
        .then((x) => (x.ok ? x.json() : null)).then((d) => { if (vivant && d) setDetails(d); }).catch(() => {});
    });
    return () => { vivant = false; };
  }, [jetonInv, cs, code, acces]);

  if (!relais) return null;
  // Le mot personnel de l'invitation est celui du coach : jamais repris au nom du participant.
  const dto = Object.assign({}, details || {}, { share_url: relais.share_url, message: '' });
  const texte = texteWhatsAppCampagne(dto);
  const surWhatsApp = () => {
    window.open(lienWhatsApp(texte), '_blank', 'noopener');
    suivreInvitation(relais.jeton, 'partage_whatsapp_declenche');
  };
  const surCopier = () => {
    copier(relais.share_url).then((ok) => setRetour(ok ? 'Lien copié' : 'Copie impossible'));
    suivreInvitation(relais.jeton, 'partage_autre_declenche');
  };
  return (
    <div data-testid="inviter-mes-amis" style={{ marginTop: '14px', padding: '14px', borderRadius: '14px', textAlign: 'left',
      background: rgbaP(0.1), border: `1px solid ${rgbaP(0.35)}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, color: 'rgba(255,255,255,0.96)', fontSize: '15px' }}>
        <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="users" size={18} /></span> Invite tes amis (facultatif)
      </div>
      <p style={{ margin: '6px 0 12px', fontSize: '13px', color: 'rgba(255,255,255,0.75)' }}>
        Voici ton lien personnel. Tes amis pourront eux aussi inviter les leurs.
      </p>
      <button type="button" data-testid="inviter-whatsapp" onClick={surWhatsApp}
              style={{ width: '100%', minHeight: '46px', borderRadius: '12px', border: 'none', background: PRIMAIRE, color: 'rgba(255,255,255,1)',
                fontWeight: 700, fontSize: '15px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '8px', cursor: 'pointer' }}>
        <SvgIcon name="send" size={18} /> Inviter sur WhatsApp
      </button>
      <button type="button" data-testid="inviter-copier" onClick={surCopier}
              style={{ width: '100%', minHeight: '44px', marginTop: '8px', borderRadius: '12px', background: 'rgba(255,255,255,0.06)',
                border: '1px solid rgba(255,255,255,0.14)', color: 'rgba(255,255,255,0.92)', fontWeight: 600, fontSize: '14px',
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '8px', cursor: 'pointer' }}>
        <SvgIcon name="copy" size={16} /> Copier mon lien
      </button>
      <p data-testid="inviter-lien" style={{ margin: '8px 0 0', fontSize: '12px', color: 'rgba(255,255,255,0.55)', wordBreak: 'break-all' }}>
        {String(relais.share_url).replace(/^https?:\/\//, '')}{retour ? ` · ${retour}` : ''}
      </p>
    </div>
  );
}

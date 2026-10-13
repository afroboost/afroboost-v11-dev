/**
 * V610o — « PARTAGER ET INVITER » : UN bouton principal, puis les canaux, WhatsApp d'abord :
 * WhatsApp · SMS · Copier le lien · Partager autrement (feuille de partage du téléphone).
 *
 * Honnêteté : ouvrir WhatsApp / SMS / la feuille = partage DÉCLENCHÉ, jamais « envoyé ».
 * Suivi : `partage_whatsapp_declenche` (WhatsApp), `partage_autre_declenche` (le reste),
 * seulement quand le canal s'ouvre vraiment. Aucun Boost ici : un Boost naît d'une
 * réservation CONFIRMÉE de l'ami, côté serveur.
 * Couleurs : var(--primary-color) ; icônes SVG.
 */
import React, { useState } from 'react';
import SvgIcon from './SvgIcon';
import { suivreInvitation } from '../utils/invitationSuivi';
import { lienWhatsApp, copier } from '../utils/parrainage';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;

const bouton = (principal) => ({
  width: '100%', minHeight: principal ? '54px' : '46px', borderRadius: '14px', cursor: 'pointer',
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '10px',
  fontWeight: principal ? 800 : 700, fontSize: principal ? '17px' : '15px',
  border: principal ? 'none' : `1px solid ${rgbaP(0.4)}`,
  background: principal ? PRIMAIRE : 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,1)',
  boxShadow: principal ? `0 8px 24px ${rgbaP(0.35)}` : 'none',
});

export default function PartagerInviter({ jeton, lien, texte, inerte = false, ouvertInitial = false, contexte = null }) {
  const [ouvert, setOuvert] = useState(!!ouvertInitial);
  const [retour, setRetour] = useState('');
  const nav = typeof navigator !== 'undefined' ? navigator : null;
  const natif = !!(nav && typeof nav.share === 'function');
  const suivre = (ev) => { if (!inerte && jeton) suivreInvitation(jeton, ev); };

  const surWhatsApp = () => {
    if (inerte) return;
    window.open(lienWhatsApp(texte), '_blank', 'noopener');
    suivre('partage_whatsapp_declenche');
  };
  const surSms = () => {
    if (inerte) return;
    // `sms:?&body=` : accepté par iOS et Android.
    window.location.href = `sms:?&body=${encodeURIComponent(texte || '')}`;
    suivre('partage_autre_declenche');
  };
  const surCopier = () => {
    if (inerte) return;
    copier(lien).then((ok) => setRetour(ok ? 'Lien copié' : 'Copie impossible'));
    suivre('partage_autre_declenche');
  };
  const surAutrement = () => {
    if (inerte) return;
    if (natif) {
      nav.share({ title: 'Afroboost', text: texte })
        .then(() => suivre('partage_autre_declenche'))
        .catch(() => { /* annulé : rien n'est compté */ });
      return;
    }
    copier(texte).then((ok) => { setRetour(ok ? 'Message copié' : 'Copie impossible'); if (ok) suivre('partage_autre_declenche'); });
  };

  return (
    <div data-testid="partager-inviter">
      <button type="button" data-testid="inviter-partager" onClick={() => setOuvert((v) => !v)} aria-expanded={ouvert} style={Object.assign(bouton(true), { marginTop: '10px' })}>
        <SvgIcon name="share" size={20} /> Partager et inviter
      </button>
      {ouvert && contexte ? (
        // V610p — PARRAINAGE CONTEXTUEL : CET événement, déjà choisi (jamais une séance à
        // choisir, jamais « essai gratuit »). Prix = celui du SERVEUR au moment présent.
        <div data-testid="partager-contexte" style={{ marginTop: '12px', padding: '12px', borderRadius: '12px', background: 'rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 800, fontSize: '15px' }}>
            Invite un ami à {contexte.titre}
            <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="fire" size={15} /></span>
            <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="headphones" size={15} /></span>
          </div>
          {contexte.quand || contexte.ville ? (
            <p style={{ margin: '4px 0 0', fontSize: '13.5px', color: 'rgba(255,255,255,0.82)' }}>{[contexte.quand, contexte.ville].filter(Boolean).join(' · ')}</p>
          ) : null}
          {contexte.prix ? <p data-testid="partager-contexte-prix" style={{ margin: '4px 0 0', fontSize: '13.5px' }}>Tarif actuel de l’événement : <strong>{contexte.prix}</strong></p> : null}
          {contexte.places ? (
            <p style={{ margin: '6px 0 0', fontSize: '13.5px', fontWeight: 800, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="fire" size={14} /></span> {contexte.places}
            </p>
          ) : null}
          {contexte.plusTot ? <p style={{ margin: '4px 0 0', fontSize: '13px', color: 'rgba(255,255,255,0.8)' }}>Plus tu réserves tôt, moins c’est cher.</p> : null}
        </div>
      ) : null}
      {ouvert ? (
        <div data-testid="partager-canaux" style={{ display: 'grid', gap: '8px', marginTop: '10px' }}>
          <button type="button" data-testid="inviter-whatsapp" onClick={surWhatsApp} style={bouton(false)}>
            <SvgIcon name="messageCircle" size={18} /> WhatsApp
          </button>
          <button type="button" data-testid="inviter-sms" onClick={surSms} style={bouton(false)}>
            <SvgIcon name="messageSquare" size={18} /> SMS
          </button>
          <button type="button" data-testid="inviter-copier" onClick={surCopier} style={bouton(false)}>
            <SvgIcon name="copy" size={18} /> Copier mon lien
          </button>
          <button type="button" data-testid="inviter-autrement" onClick={surAutrement} style={bouton(false)}>
            <SvgIcon name={natif ? 'share' : 'link'} size={18} /> {natif ? 'Partager autrement' : 'Copier le message'}
          </button>
        </div>
      ) : (
        <button type="button" data-testid="inviter-copier-direct" onClick={surCopier}
                style={{ width: '100%', minHeight: '44px', marginTop: '8px', borderRadius: '12px', background: 'none', border: 'none',
                  color: 'rgba(255,255,255,0.85)', fontWeight: 600, fontSize: '14px', display: 'inline-flex', alignItems: 'center',
                  justifyContent: 'center', gap: '8px', cursor: 'pointer' }}>
          <SvgIcon name="copy" size={16} /> Copier mon lien
        </button>
      )}
      <p data-testid="inviter-lien" style={{ margin: '8px 0 0', fontSize: '12px', color: 'rgba(255,255,255,0.55)', wordBreak: 'break-all' }}>
        {String(lien || '').replace(/^https?:\/\//, '')}{retour ? ` · ${retour}` : ''}
      </p>
    </div>
  );
}

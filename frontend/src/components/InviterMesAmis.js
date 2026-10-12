/**
 * V607 — « INVITE TES AMIS » APRÈS UN ÉVÉNEMENT (facultatif, jamais bloquant).
 *
 * Affiché dans la confirmation de paiement (événement payant) ou d'inscription
 * (événement gratuit), SEULEMENT si la personne est arrivée par une invitation
 * (`af_invitation`, posé par `?inv=`). Le serveur lui donne SON lien personnel
 * (`/i/<jeton>`, génération suivante) : par la session Stripe payée, ou par son
 * accès récent DANS SON ESPACE (session d'espace prouvée par le code e-mail). Sans invitation, ou si le serveur ne répond pas : RIEN
 * n'est affiché (aucune autre confirmation n'est modifiée).
 *
 * Honnêteté : le clic WhatsApp OUVRE WhatsApp avec le message prérempli ; on
 * enregistre « partage déclenché », jamais « envoyé ». Aucun envoi automatique.
 */
import React, { useEffect, useRef, useState } from 'react';
import AfroboostAudioPlayer from './AfroboostAudioPlayer'; // V610g
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

/** V610d — un fichier Afroboost (`/api/files/...`) ou une adresse https ; sinon rien. */
function urlAudioSure(u) {
  const v = String(u || '').trim();
  if (/^\/api\/files\/[^\s"'<>]+$/.test(v) && !v.startsWith('//')) return v;
  if (/^https:\/\/[A-Za-z0-9.-]+(:\d+)?\/[^\s"'<>]*$/.test(v)) return v;
  return '';
}

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

async function lienParInscription(jeton, code, jetonEspace, slug) {
  try {
    // La session d'ESPACE (code e-mail prouvé) est exigée : un code d'accès seul ne suffit pas.
    const r = await fetch(`${BACKEND_URL}/api/invitation/relais/inscription`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'x-espace-token': jetonEspace },
      body: JSON.stringify({ jeton, code, slug: slug || '' }),
    });
    return r.ok ? r.json() : null;
  } catch (e) { return null; }
}

export default function InviterMesAmis({ sessionId, codeAcces, jetonEspace, slug, relaisInitial, evenement, apercuDetails, autoLecture }) {
  // V610e : `apercuDetails` (éditeur coach) — le bloc tel que l'invité le verra après sa
  // réservation, SANS appel réseau, sans partage ni suivi (boutons inertes).
  const enApercu = !!apercuDetails;
  // V610 : `relaisInitial` = lien déjà rendu par le serveur (place offerte d'un membre) ;
  // `evenement` = billet d'un événement à réservation automatique : son lien existe
  // même sans invitation d'origine (rattaché à l'invitation du coach).
  const [relaisEtat, setRelais] = useState(relaisInitial && relaisInitial.jeton ? relaisInitial : null);
  const relais = enApercu ? { jeton: 'apercu', share_url: 'https://afroboost.com/i/ton-lien-personnel' } : relaisEtat;
  const [detailsEtat, setDetails] = useState(null);
  const details = enApercu ? apercuDetails : detailsEtat;
  const [retour, setRetour] = useState('');
  const inv = invitationActuelle();
  const jetonInv = inv ? inv.t : '';
  const cs = /^cs_[A-Za-z0-9_]+$/.test(String(sessionId || '')) ? String(sessionId) : '';
  const acces = /^[A-Za-z0-9-]{4,40}$/.test(String(codeAcces || '')) && jetonEspace ? String(codeAcces) : '';
  const espace = String(jetonEspace || '');
  const membre = String(slug || '');

  const jetonInitial = relaisInitial && relaisInitial.jeton ? String(relaisInitial.jeton) : '';
  useEffect(() => {
    if (enApercu) return undefined;
    if (jetonInitial) {
      let vivant = true;
      fetch(`${BACKEND_URL}/api/invitation/publique/${encodeURIComponent(jetonInitial)}`)
        .then((x) => (x.ok ? x.json() : null)).then((d) => { if (vivant && d) setDetails(d); }).catch(() => {});
      return () => { vivant = false; };
    }
    const parSession = !!cs && (!!jetonInv || !!evenement);
    if (!parSession && !(jetonInv && acces)) return undefined;
    let vivant = true;
    const demande = parSession ? lienParSession(cs) : lienParInscription(jetonInv, acces, espace, membre);
    demande.then((r) => {
      if (!vivant || !r || !r.jeton) return;
      setRelais(r);
      fetch(`${BACKEND_URL}/api/invitation/publique/${encodeURIComponent(r.jeton)}`)
        .then((x) => (x.ok ? x.json() : null)).then((d) => { if (vivant && d) setDetails(d); }).catch(() => {});
    });
    return () => { vivant = false; };
  }, [jetonInitial, jetonInv, cs, acces, espace, membre, evenement, enApercu]);

  // V610d / V610g — « DEVIENS AFROBOOSTEUR » : l'audio d'APRÈS réservation (événement payant
  // seulement), joué par le lecteur Afroboost.
  const audioPartage = details && details.type === 'event_paid' ? urlAudioSure(details.audio_partage_url) : '';
  // V610m — sur l'écran de confirmation (`autoLecture`) : UNE tentative de lecture dès que
  // le message est là ; refus du navigateur -> le lecteur visible (« Écouter le message »).
  // Jamais en boucle, jamais relancé.
  const audioRef = useRef(null);
  const audioTente = useRef(false);
  const pret = !!(relais && audioPartage);
  useEffect(() => {
    if (enApercu || !autoLecture || !pret || audioTente.current) return undefined;
    const t = setTimeout(() => {
      if (audioTente.current || !audioRef.current) return;
      audioTente.current = true;
      try { audioRef.current.lire().catch(() => { /* bloqué : le lecteur visible prend le relais */ }); } catch (e) { /* ignore */ }
    }, 0);
    return () => clearTimeout(t);
  }, [enApercu, autoLecture, pret]);

  if (!relais) return null;
  // Le mot personnel de l'invitation est celui du coach : jamais repris au nom du participant.
  const dto = Object.assign({}, details || {}, { share_url: relais.share_url, message: '' });
  const texte = texteWhatsAppCampagne(dto);
  const surWhatsApp = () => {
    if (enApercu) return;
    window.open(lienWhatsApp(texte), '_blank', 'noopener');
    suivreInvitation(relais.jeton, 'partage_whatsapp_declenche');
  };
  const surCopier = () => {
    if (enApercu) return;
    copier(relais.share_url).then((ok) => setRetour(ok ? 'Lien copié' : 'Copie impossible'));
    suivreInvitation(relais.jeton, 'partage_autre_declenche');
  };
  // V610m — ÉVÉNEMENT PAYANT (paiement ou place offerte confirmés) : le bloc « Deviens
  // Afroboosteur » est TOUJOURS celui-ci — audio s'il est configuré, et le gros bouton.
  if (audioPartage || (details && details.type === 'event_paid')) {
    return (
      <div data-testid="inviter-mes-amis" data-variante="afroboosteur" style={{ marginTop: '14px', padding: '16px 14px', borderRadius: '16px', textAlign: 'left',
        background: rgbaP(0.12), border: `1px solid ${rgbaP(0.4)}` }}>
        <div data-testid="afroboosteur-titre" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 800, color: 'rgba(255,255,255,0.97)', fontSize: '18px' }}>
          <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="fire" size={22} /></span> Deviens Afroboosteur
        </div>
        <p data-testid="afroboosteur-texte" style={{ margin: '4px 0 12px', fontSize: '14px', color: 'rgba(255,255,255,0.85)', lineHeight: 1.45 }}>
          Fais circuler l’énergie. Invite tes amis à vivre Afroboost avec toi.
        </p>
        {audioPartage ? (
          <AfroboostAudioPlayer ref={audioRef} src={audioPartage} testidAudio="afroboosteur-audio" testidBouton="afroboosteur-ecouter" inerte={enApercu} />
        ) : null}
        <button type="button" data-testid="inviter-whatsapp" onClick={surWhatsApp}
                style={{ width: '100%', minHeight: '54px', marginTop: '10px', borderRadius: '14px', border: 'none', background: PRIMAIRE,
                  color: 'rgba(255,255,255,1)', fontWeight: 800, fontSize: '17px', display: 'inline-flex', alignItems: 'center',
                  justifyContent: 'center', gap: '10px', cursor: 'pointer', boxShadow: `0 8px 24px ${rgbaP(0.35)}` }}>
          <SvgIcon name="send" size={20} /> Inviter mes amis
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

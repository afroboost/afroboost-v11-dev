// =====================================================================
// LIVE RAPIDE — LA porte unique vers le live BoostTribe, réutilisable.
//
// Avant : le seul chemin était Publier -> modale -> « Sessions live » ->
// Rejoindre -> hub -> Live Visio. La logique (jeton d'accès, iframe, écoute
// des postMessage) vivait dans `BoostTribeSection` (Publications.js) et ne
// pouvait servir nulle part ailleurs. Elle est ICI, en un hook :
//
//   const live = useBoostTribeLive();
//   live.ouvrir({ subscriberCode })   -> POST /api/boosttribe/access -> overlay
//   <BoostTribeLiveOverlay live={live} />
//
// Il n'y a toujours qu'UN système Live : le serveur décide (admin -> jeton
// admin ; code abonné avec crédit -> jeton abonné ; sinon refus), l'iframe
// est la même, l'URL vient de BOOSTTRIBE_EMBED_URL. Ce module n'ajoute que
// deux choses : (1) le coach ANNONCE à Afroboost le début / la fin de son live
// (`bt:session-started` / `bt:session-ended` avec `session_code`, `is_host`)
// pour que la barre affiche « LIVE EN COURS » et que les suivants entrent
// directement dans la bonne session ; (2) un état lisible par n'importe quel
// bouton.
//
// ORIGINES DES MESSAGES : l'iframe est servie par boosttribe.pro OU par
// afroboost.com/live (même origine que la page) — les deux sont acceptées,
// et rien d'autre. Avant, seule boosttribe.pro l'était : en production
// (afroboost.com/live) les messages étaient IGNORÉS et le crédit ne se
// rafraîchissait jamais.
// =====================================================================
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { authValide } from '../../utils/authSession';
import { lireSession as lireSessionEspace } from '../../utils/espaceSession';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;
const BT_ORIGIN = 'https://boosttribe.pro';

export const EVENEMENT_LIVE = 'afroboost:live-status';

function origineAcceptee(origin) {
  if (origin === BT_ORIGIN) return true;
  try { return origin === window.location.origin; } catch (e) { return false; }
}

/** Le code abonné connu du navigateur, sans réseau : session d'espace, puis identité chat. */
export function codeAbonneLocal() {
  const s = lireSessionEspace();
  if (s && s.code) return String(s.code);
  try {
    const brut = localStorage.getItem('afroboost_identity') || localStorage.getItem('af_chat_client');
    if (brut) {
      const j = JSON.parse(brut);
      const c = (j && (j.code || j.subscriber_code || j.access_code)) || '';
      if (c && String(c).indexOf('@') === -1) return String(c);
    }
  } catch (e) { /* stockage illisible : aucun code */ }
  return '';
}

/** L'e-mail identifié via le ChatWidget (participant), s'il existe. */
export function emailIdentiteLocale() {
  try {
    const brut = localStorage.getItem('afroboost_identity') || localStorage.getItem('af_chat_client');
    if (!brut) return '';
    const j = JSON.parse(brut);
    return String((j && (j.email || j.userEmail)) || '').trim();
  } catch (e) { return ''; }
}

/**
 * Résout le code abonné à envoyer au serveur. Même chemin que le bouton
 * « Publier » de l'espace abonné (V292/V294) : code local, sinon les
 * abonnements actifs par e-mail via l'endpoint existant. Jamais de saisie.
 */
export async function resoudreCodeAbonne() {
  const local = codeAbonneLocal();
  if (local) return local;
  const email = emailIdentiteLocale();
  if (!email) return '';
  try {
    const r = await axios.get(`${API}/discount-codes/subscriptions/status`, { params: { email } });
    if (r.data && r.data.codes_masked) return '';   // V296 : pas de preuve d'appareil -> code masqué
    const bruts = (r.data && (r.data.subscriptions || (r.data.subscription ? [r.data.subscription] : []))) || [];
    // Même déduplication par code que la réservation (v151) et que « Publier ».
    const vus = {}; const actives = [];
    bruts.forEach((x) => { const k = ((x && x.code) || '').toUpperCase(); if (!k || vus[k]) return; vus[k] = true; actives.push(x); });
    return actives.length ? String(actives[0].code) : '';
  } catch (e) { return ''; }
}

export function useBoostTribeLive() {
  const [state, setState] = useState('idle');   // idle | loading | denied | live
  const [reason, setReason] = useState('');       // subscription_required | no_credit
  const [embedUrl, setEmbedUrl] = useState('');
  const [kind, setKind] = useState('');           // admin | subscriber
  const sessionRef = useRef({ code: '', isHost: false });

  // Le coach annonce son live à Afroboost (jeton signé requis côté serveur).
  const annoncer = useCallback(async (event, code) => {
    if (!code || !authValide()) return;
    try {
      await axios.post(`${API}/boosttribe/live-status`, { event, session_code: code });
      window.dispatchEvent(new CustomEvent(EVENEMENT_LIVE, { detail: { active: event === 'started' } }));
    } catch (e) { /* annonce impossible : le live, lui, continue */ }
  }, []);

  useEffect(() => {
    const onMsg = (event) => {
      if (!origineAcceptee(event.origin)) return;
      const d = event.data || {};
      const t = d.type;
      if (t === 'bt:session-started') {
        window.dispatchEvent(new CustomEvent('afroboost:credit-refresh'));
        if (d.is_host && d.session_code) {
          sessionRef.current = { code: String(d.session_code), isHost: true };
          annoncer('started', sessionRef.current.code);
        }
      } else if (t === 'bt:session-ended') {
        if (d.is_host && d.session_code) annoncer('ended', String(d.session_code));
        setState('idle');
      }
    };
    window.addEventListener('message', onMsg);
    return () => window.removeEventListener('message', onMsg);
  }, [annoncer]);

  const ouvrir = useCallback(async (options) => {
    const opts = options || {};
    setState('loading');
    setReason('');
    try {
      // V280 (revue sécurité) : code dans le CORPS (POST), jamais en query string.
      const payload = {};
      const code = opts.subscriberCode || '';
      if (code && code.indexOf('@') === -1) payload.subscriber_code = code;
      const res = await axios.post(`${API}/boosttribe/access`, payload);
      setEmbedUrl(res.data.embedUrl);
      setKind((res.data.live && res.data.live.kind) || '');
      setState('live');
      return { ok: true };
    } catch (err) {
      const r = err && err.response;
      const motif = (r && r.data && r.data.reason) || 'subscription_required';
      setReason(motif);
      setState('denied');
      return { ok: false, reason: motif };
    }
  }, []);

  const fermer = useCallback(() => {
    // Le coach ferme l'overlay : son live n'est plus « en cours » pour Afroboost.
    if (sessionRef.current.isHost && sessionRef.current.code) {
      annoncer('ended', sessionRef.current.code);
      sessionRef.current = { code: '', isHost: false };
    }
    setState('idle');
  }, [annoncer]);

  return { state, reason, embedUrl, kind, ouvrir, fermer, setState };
}

export const iconLive = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="23 7 16 12 23 17 23 7" />
    <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
  </svg>
);

/** L'overlay plein écran avec l'iframe (caméra/micro autorisés). Rendu dans <body>. */
export function BoostTribeLiveOverlay({ live }) {
  if (live.state !== 'live' || !live.embedUrl) return null;
  return createPortal(
    <div style={{ position: 'fixed', inset: 0, background: '#000', zIndex: 2147483000, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: '#0a0a0a' }}>
        <span style={{ color: '#fff', fontSize: 13, fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 8 }}>{iconLive} BoostTribe live</span>
        <button onClick={live.fermer} style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 6 }} aria-label="Fermer" title="Fermer">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
        </button>
      </div>
      <iframe
        src={live.embedUrl}
        allow="camera; microphone; autoplay; fullscreen; display-capture; clipboard-write"
        style={{ flex: 1, width: '100%', border: 0 }}
        title="BoostTribe live"
      />
    </div>,
    document.body
  );
}

/**
 * « Un live est-il en cours ? » — sondage léger de GET /boosttribe/live-status,
 * onglet visible seulement (règle CHAT-LOOP), et jamais de setState si rien
 * n'a changé. Écoute aussi l'annonce locale du coach (EVENEMENT_LIVE).
 */
export function useLiveEnCours(intervalleMs) {
  const [actif, setActif] = useState(false);
  useEffect(() => {
    let vivant = true;
    const lire = async () => {
      if (document.visibilityState !== 'visible') return;
      try {
        const r = await axios.get(`${API}/boosttribe/live-status`);
        const a = !!(r.data && r.data.active);
        if (vivant) setActif((prev) => (prev === a ? prev : a));
      } catch (e) { /* réseau : on garde l'état connu */ }
    };
    lire();
    const timer = setInterval(lire, intervalleMs || 60000);
    const onLocal = (ev) => { const a = !!(ev.detail && ev.detail.active); setActif((prev) => (prev === a ? prev : a)); };
    const onVisible = () => { if (document.visibilityState === 'visible') lire(); };
    window.addEventListener(EVENEMENT_LIVE, onLocal);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      vivant = false;
      clearInterval(timer);
      window.removeEventListener(EVENEMENT_LIVE, onLocal);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [intervalleMs]);
  return actif;
}

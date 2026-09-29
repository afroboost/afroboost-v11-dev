/**
 * PAR-2 — « INVITATION & PARRAINAGE » DEPUIS L'ESPACE ABONNÉ (LOT 1).
 *
 * LE MÊME PARCOURS QUE /parrainage, PAS UN SECOND SYSTÈME : on rend
 * l'assistant EXISTANT (InvitationWizard) sur le pass courant de GET /me —
 * y compris l'invitation enfant de chaîne liée à l'abonné après son
 * inscription — sinon sa création Pass Duo (règles inchangées).
 *
 * RÉSEAU : UN GET /me + lireConfigParrainage() au montage, jamais relancés
 * (effet sans dépendance). Ensuite uniquement sur geste : POST /invitations
 * (journal d'un partage) ; les POST /pass et PUT /pass/{id}/invitation sont
 * ceux de l'assistant, dont la réponse remonte par `onPass`.
 *
 * STATUT : déduit des SEULS champs publics du PassDTO (status, invitee présent
 * ou non) et du journal invitations[] de /me. Aucune donnée du filleul n'est
 * rendue — pas même son prénom. `chain.shared_at` n'est PAS exposé par le
 * PassDTO : un partage de chaîne compte ici via invitations[] ou `waiting`.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { QRCodeCanvas } from 'qrcode.react';
import SvgIcon from '../SvgIcon';
import InvitationWizard from './InvitationWizard';
import ParrainageDrawer from './ParrainageDrawer';
import {
  API_PARRAINAGE, enteteParrain, aUneIdentiteParrain, lireConfigParrainage, passCourant, urlEspaceCourant,
} from '../../utils/parrainage';
import './parrainage.css';

/**
 * Statut simple d'une invitation, sans aucune donnée privée.
 * @returns {null|{cle:'a_partager'|'partagee'|'debloque', libelle:string, amiRejoint:boolean}}
 */
export function statutInvitation(pass, invitations) {
  if (!pass || !pass.id) return null;
  const s = pass.status;
  const amiRejoint = !!pass.invitee || s === 'friend_registered';
  if (s === 'unlocked' || s === 'used') return { cle: 'debloque', libelle: 'Avantage débloqué', amiRejoint };
  const journalise = (Array.isArray(invitations) ? invitations : []).some((i) => i && i.pass_id === pass.id);
  // PAR : `chain_shared` (booléen du serveur, sans PII) couvre le partage fait par la chaîne.
  if (s === 'waiting' || s === 'friend_registered' || journalise || pass.chain_shared === true) {
    return { cle: 'partagee', libelle: 'Partagée', amiRejoint };
  }
  return { cle: 'a_partager', libelle: 'À partager', amiRejoint };
}

const ICONES = { a_partager: 'share', partagee: 'hourglass', debloque: 'check' };
const CHIPS = { a_partager: 'cp-chip', partagee: 'cp-chip cp-chip--wait', debloque: 'cp-chip cp-chip--ok' };

/** QR du lien partagé, rendu dans <body> (hors du tiroir animé). Échap ferme. */
function ModaleQr({ url, onClose }) {
  const fermer = useRef(onClose);
  fermer.current = onClose;
  useEffect(() => {
    const surTouche = (e) => { if (e.key === 'Escape') { e.stopPropagation(); fermer.current(); } };
    document.addEventListener('keydown', surTouche, true);
    return () => document.removeEventListener('keydown', surTouche, true);
  }, []);
  return createPortal(
    <div className="cp-root">
      <div className="cp-modal-bg" role="dialog" aria-modal="true" aria-label="QR code de ton invitation"
           onClick={() => fermer.current()} data-testid="invitation-parrainage-qr">
        <div className="cp-modal" onClick={(e) => e.stopPropagation()}>
          <div className="cp-eyebrow">Ton invitation</div>
          <p className="cp-mini">Ton ami scanne ce code pour ouvrir ton invitation.</p>
          <div className="cp-qr-big">
            <QRCodeCanvas value={url} size={180} level="M" includeMargin={false} bgColor="#ffffff" fgColor="#000000" />
          </div>
          <button type="button" className="cp-b cp-b--ghost" onClick={() => fermer.current()}>Fermer</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

/**
 * @param {function} onFermer  facultatif : bouton « Plus tard »
 * @param {boolean}  compact   dans le tiroir : pas de grand titre (le tiroir en a un)
 */
export default function InvitationParrainage({ onFermer, compact }) {
  const [etat, setEtat] = useState('chargement'); // chargement | non_connecte | desactive | erreur | ok
  const [me, setMe] = useState(null);
  const [courses, setCourses] = useState([]);
  const [creationForcee, setCreationForcee] = useState(false);
  const [qrUrl, setQrUrl] = useState('');

  // UN chargement au montage : /me + configuration. Jamais relancé.
  useEffect(() => {
    let vivant = true;
    if (!aUneIdentiteParrain()) { setEtat('non_connecte'); return undefined; }
    Promise.all([
      axios.get(`${API_PARRAINAGE}/me`, { headers: enteteParrain(), timeout: 10000 })
        .then((r) => ({ ok: true, data: r.data }))
        .catch((e) => ({ ok: false, status: e && e.response && e.response.status })),
      lireConfigParrainage(),
    ]).then(([rep, cfg]) => {
      if (!vivant) return;
      if (!rep.ok) {
        setEtat(rep.status === 401 || rep.status === 403 ? 'non_connecte' : rep.status === 404 ? 'desactive' : 'erreur');
        return;
      }
      const d = rep.data || {};
      if (d.enabled === false || !cfg.enabled) { setEtat('desactive'); return; }
      setCourses(Array.isArray(cfg.courses) ? cfg.courses : []);
      setMe(d);
      setEtat('ok');
    });
    return () => { vivant = false; };
  }, []);

  /** Remplace (ou ajoute) un pass depuis une réponse serveur — jamais de relecture de /me. */
  const poserPass = useCallback((dto) => {
    if (!dto || !dto.id) return;
    setMe((prev) => {
      if (!prev) return prev;
      const liste = Array.isArray(prev.passes) ? prev.passes : [];
      const idx = liste.findIndex((p) => p && p.id === dto.id);
      const suivant = idx >= 0 ? liste.map((p, i) => (i === idx ? dto : p)) : [dto].concat(liste);
      return Object.assign({}, prev, { passes: suivant });
    });
    setCreationForcee(false);
  }, []);

  /** Journal d'un partage (geste) ; `locked` → `waiting` localement, comme le Centre. */
  const journaliser = useCallback((pass, channel) => {
    if (!pass || !pass.id) return Promise.resolve();
    return axios.post(`${API_PARRAINAGE}/invitations`, { pass_id: pass.id, channel }, { headers: enteteParrain() })
      .then((r) => {
        const d = (r && r.data) || {};
        setMe((prev) => {
          if (!prev) return prev;
          const invitations = [{ id: d.id || `local-${Date.now()}`, pass_id: pass.id, channel, created_at: new Date().toISOString() }]
            .concat(Array.isArray(prev.invitations) ? prev.invitations : []);
          const passes = (Array.isArray(prev.passes) ? prev.passes : []).map((p) => {
            if (!p || p.id !== pass.id) return p;
            const maj = {};
            if (typeof d.share_url === 'string' && d.share_url) maj.share_url = d.share_url;
            if (typeof d.card_url === 'string' && d.card_url) maj.card_url = d.card_url;
            if (p.status === 'locked') Object.assign(maj, { status: 'waiting', status_label: 'En attente de ton ami' });
            return Object.keys(maj).length ? Object.assign({}, p, maj) : p;
          });
          return Object.assign({}, prev, { invitations, passes });
        });
      })
      .catch(() => { /* le partage a eu lieu ; le journal n'est pas bloquant */ });
  }, []);

  const surQr = (pass, url) => {
    if (!pass || !url) return;
    setQrUrl(url);
    journaliser(pass, 'qr');
  };

  const lienTout = (
    <a className="cp-b cp-b--ghost" href="/parrainage" data-testid="invitation-parrainage-tout">
      <SvgIcon name="arrowRight" size={18} /> Voir tout mon parrainage
    </a>
  );
  const plusTard = typeof onFermer === 'function' ? (
    <button type="button" className="cp-b cp-b--ghost" onClick={onFermer} data-testid="invitation-parrainage-fermer">
      Plus tard
    </button>
  ) : null;

  let corps;
  if (etat === 'chargement') {
    corps = (
      <div className="cp-state" data-testid="invitation-parrainage-chargement">
        <div className="cp-spinner" aria-hidden="true" />
        <p className="cp-lead">Ton invitation arrive…</p>
      </div>
    );
  } else if (etat === 'non_connecte') {
    const urlEspace = urlEspaceCourant();
    corps = (
      <div className="cp-state" data-testid="invitation-parrainage-non-connecte">
        <p className="cp-lead cp-center">Ta session a expiré : rouvre ton espace abonné pour inviter un ami.</p>
        {urlEspace ? <a className="cp-b" href={urlEspace}>Ouvrir mon espace abonné</a> : null}
      </div>
    );
  } else if (etat === 'desactive') {
    corps = (
      <div className="cp-state" data-testid="invitation-parrainage-desactive">
        <p className="cp-lead cp-center">Le Parrainage Afroboost ouvre prochainement. Reviens bientôt.</p>
      </div>
    );
  } else if (etat === 'erreur') {
    corps = (
      <div className="cp-state" data-testid="invitation-parrainage-erreur">
        <p className="cp-lead cp-center">Impossible de charger ton invitation. Vérifie ta connexion et réessaie.</p>
      </div>
    );
  } else {
    const passes = Array.isArray(me.passes) ? me.passes : [];
    const courant = passCourant(passes);
    const statut = creationForcee ? null : statutInvitation(courant, me.invitations);
    corps = (
      <>
        {statut ? (
          <div className="cp-prog" style={{ margin: '12px 0 4px', flexWrap: 'wrap', gap: 8 }}>
            <span className={CHIPS[statut.cle]} data-testid="invitation-parrainage-statut" data-statut={statut.cle}>
              <SvgIcon name={ICONES[statut.cle]} size={12} strokeWidth="2.5" />
              {statut.libelle}
            </span>
            {statut.amiRejoint ? (
              <span className="cp-mini" data-testid="invitation-parrainage-ami" style={{ margin: 0 }}>
                Ton ami a rejoint Afroboost
              </span>
            ) : null}
          </div>
        ) : null}
        <InvitationWizard
          courses={courses}
          passOuvert={courant}
          contexte={null}
          creationForcee={creationForcee}
          onRetour={() => setCreationForcee(false)}
          onPass={poserPass}
          onJournal={journaliser}
          onQr={surQr}
        />
        {statut && statut.cle === 'debloque' && !creationForcee ? (
          <button type="button" className="cp-b cp-b--secondary" onClick={() => setCreationForcee(true)}
                  data-testid="invitation-parrainage-nouveau">
            <SvgIcon name="users" size={18} /> Inviter un autre ami
          </button>
        ) : null}
      </>
    );
  }

  return (
    <div className="cp-root" data-testid="invitation-parrainage">
      {!compact ? <h2 className="cp-h2">Invitation &amp; parrainage</h2> : null}
      {corps}
      {etat === 'ok' ? lienTout : null}
      {plusTard}
      {qrUrl ? <ModaleQr url={qrUrl} onClose={() => setQrUrl('')} /> : null}
    </div>
  );
}

/**
 * Le tiroir existant (ParrainageDrawer) qui porte le parcours, dans une racine
 * `cp-root` (les jetons de couleur du tiroir y sont définis).
 */
export function TiroirInvitationParrainage({ onFermer, declencheur }) {
  return (
    <div className="cp-root">
      <ParrainageDrawer titre="Invitation & parrainage" outil="invitation" declencheur={declencheur} onClose={onFermer}>
        <InvitationParrainage compact onFermer={onFermer} />
      </ParrainageDrawer>
    </div>
  );
}

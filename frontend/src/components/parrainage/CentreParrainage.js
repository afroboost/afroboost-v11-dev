/**
 * V534 — CENTRE PARRAINAGE (page /parrainage).
 *
 * LA HIÉRARCHIE DE LA MAQUETTE, RIEN D'AUTRE :
 *   Parrainage → Mes résultats → Inviter un ami [WhatsApp / Copier / QR /
 *   Partager] → Mes programmes [Carte 1 Parrainage crédits, Carte 2 Pass Duo]
 *   → Mes invitations → Historique.
 *
 * RÉSEAU : `GET /api/referral/me` UNE fois au montage (en-tête `enteteParrain()`),
 * plus la configuration (cache 10 min). Après chaque POST, l'état local est
 * mis à jour DEPUIS LA RÉPONSE — on ne relance jamais /me en boucle.
 *
 * ÉTATS DE PAGE : chargement / non connecté / désactivé (« Bientôt
 * disponible ») / centre complet.
 *
 * V552 — PAGE COMPACTE : en-tête, résultats, « Inviter un ami » (l'assistant,
 * prioritaire, toujours monté), puis « Mes outils » : quatre raccourcis
 * (Crédits, Pass Duo, Invitations, Historique). Chaque raccourci ouvre LE MÊME
 * `ParrainageDrawer`, qui affiche le bloc COMPLET d'avant (rien de supprimé).
 * Le tiroir est rendu à côté de l'assistant, jamais à sa place ; il ne fait
 * aucun appel : tout vient du GET /me du montage.
 *
 * CE QU'ON N'AFFICHE PAS : « crédits Spordateur gagnés » — la donnée n'est
 * pas disponible proprement côté Afroboost ; la Carte 1 renvoie au profil
 * Spordateur, source de vérité, sans rien inventer.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { QRCodeCanvas } from 'qrcode.react';
import SvgIcon from '../SvgIcon';
import PassDuoCard, { ChipStatut } from './PassDuoCard';
import InvitationWizard from './InvitationWizard'; // V551 — l'invitation personnalisée, en 3 étapes
import ParrainageDrawer from './ParrainageDrawer'; // V552 — le tiroir commun de « Mes outils »
import { entrerDansSpordate, prechargerSpordate } from '../../utils/spordateHandoff';
import {
  API_PARRAINAGE, enteteParrain, aUneIdentiteParrain, urlEspaceCourant, lireConfigParrainage,
  lireContexteUrl, passCourant, libelleJour, libelleDateCourte, STATUTS_OUVERTS,
  changerOffre, lireRefus, messageRefusOffre, lignesHistorique, offreDuPass, TEXTE_OFFRE_CONFLIT, // V534b
  changerSeance, // V539b — le parrain peut aussi changer la date de son Pass
  LIBELLES_STATUT, // V552 — l'état du Pass sur son raccourci
} from '../../utils/parrainage';
import './parrainage.css';

/** V552 — les quatre raccourcis de « Mes outils », dans l'ordre d'affichage. */
export const OUTILS = [
  { id: 'credits', titre: 'Crédits', icone: 'dollarSign' },
  { id: 'pass', titre: 'Pass Duo', icone: 'users' },
  { id: 'invitations', titre: 'Invitations', icone: 'send' },
  { id: 'historique', titre: 'Historique', icone: 'clock' },
];

/** V552 — la petite ligne d'état sous chaque raccourci (aucune donnée inventée). */
export function etatsOutils({ passes, passLien, invitations, history }) {
  const nInv = (invitations || []).length;
  const nHist = (history || []).length;
  let pass = 'Aucun';
  if (passLien) pass = LIBELLES_STATUT[passLien.status] || 'En cours';
  else if ((passes || []).length) pass = 'Aucun en cours';
  return {
    credits: 'Sur Spordateur',
    pass,
    invitations: nInv === 0 ? 'Aucune' : `${nInv} invitation${nInv > 1 ? 's' : ''}`,
    historique: nHist === 0 ? 'Vide' : `${nHist} événement${nHist > 1 ? 's' : ''}`,
  };
}

const CANAUX = { whatsapp: 'WhatsApp', copy: 'Lien copié', qr: 'QR partagé', share: 'Partagé' };

/** Le lien sans protocole, pour l'afficher comme un code (afroboost.com/duo/…). */
export function lienAffiche(url) {
  return String(url || '').replace(/^https?:\/\//, '');
}

/** Pluriels des trois compteurs de résultats. */
export function libellesResultats(stats) {
  const s = stats || {};
  const n = (v) => Number(v) || 0;
  return [
    { valeur: n(s.invited), libelle: n(s.invited) > 1 ? 'amis invités' : 'ami invité', testid: 'stat-invited' },
    { valeur: n(s.joined), libelle: n(s.joined) > 1 ? 'amis inscrits' : 'ami inscrit', testid: 'stat-joined' },
    { valeur: n(s.unlocked), libelle: n(s.unlocked) > 1 ? 'Pass Duo débloqués' : 'Pass Duo débloqué', testid: 'stat-unlocked' },
  ];
}

function EnTete({ pill }) {
  return (
    <header className="cp-header">
      <a className="cp-logo" href="/" aria-label="Retour à l'accueil Afroboost">Afro<span>boost</span></a>
      <div className="cp-pill">{pill || 'Parrainage'}</div>
    </header>
  );
}

function Cadre({ children, pill }) {
  return (
    <div className="cp-root cp-page" data-testid="centre-parrainage">
      <main className="cp-app">
        <EnTete pill={pill} />
        {children}
        <footer className="cp-footer">Danse · Fitness · Good vibes</footer>
      </main>
    </div>
  );
}

function ModaleQr({ url, onClose }) {
  const zone = useRef(null);
  const telecharger = () => {
    const canvas = zone.current && zone.current.querySelector('canvas');
    if (!canvas) return;
    const a = document.createElement('a');
    a.download = 'pass-duo-afroboost.png';
    a.href = canvas.toDataURL('image/png');
    a.click();
  };
  return (
    <div className="cp-modal-bg" role="dialog" aria-modal="true" aria-label="QR code de ton invitation" onClick={onClose} data-testid="qr-modale">
      <div className="cp-modal" onClick={(e) => e.stopPropagation()}>
        <div className="cp-eyebrow">Ton invitation</div>
        <p className="cp-mini">Ton ami scanne ce code pour rejoindre ton Pass Duo.</p>
        <div className="cp-qr-big" ref={zone}>
          <QRCodeCanvas value={url} size={180} level="M" includeMargin={false} bgColor="#ffffff" fgColor="#000000" />
        </div>
        <div className="cp-code" style={{ fontSize: 12 }}><div>{lienAffiche(url)}</div></div>
        <button type="button" className="cp-b cp-b--secondary" onClick={telecharger} data-testid="qr-telecharger">
          <SvgIcon name="download" size={20} /> Télécharger en PNG
        </button>
        <button type="button" className="cp-b cp-b--ghost" onClick={onClose}>Fermer</button>
      </div>
    </div>
  );
}

export default function CentreParrainage() {
  const [etat, setEtat] = useState('chargement'); // chargement | non_connecte | desactive | ok | erreur
  const [me, setMe] = useState(null);
  const [config, setConfig] = useState({ enabled: false, courses: [] });
  const [passAfficheId, setPassAfficheId] = useState('');
  const [occupe, setOccupe] = useState(false);
  const [erreurPass, setErreurPass] = useState('');
  const [qrUrl, setQrUrl] = useState(''); // V551 : le QR s'ouvre depuis l'assistant, sur le lien qu'il partage
  const [creationForcee, setCreationForcee] = useState(false); // V551 : « Créer un nouveau Pass Duo »
  const [contexte] = useState(() => lireContexteUrl()); // V551 : ?course=&occurrence=&offer= (lu une fois)
  const [outil, setOutil] = useState(''); // V552 : le tiroir ouvert ('' = aucun)
  const declencheurs = useRef({});        // V552 : les raccourcis, pour y rendre le focus
  const urlEspace = urlEspaceCourant();

  // UN chargement au montage : /me + configuration. Jamais relancé ensuite.
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
      setConfig((prev) => (JSON.stringify(prev) === JSON.stringify(cfg) ? prev : cfg));
      if (!rep.ok) {
        if (rep.status === 401 || rep.status === 403) setEtat('non_connecte');
        else if (rep.status === 404) setEtat('desactive');
        else setEtat('erreur');
        return;
      }
      const d = rep.data || {};
      if (d.enabled === false || !cfg.enabled) { setEtat('desactive'); return; }
      setMe(d);
      const courant = passCourant(d.passes);
      setPassAfficheId(courant ? courant.id : (d.passes && d.passes[0] ? d.passes[0].id : ''));
      setEtat('ok');
    });
    return () => { vivant = false; };
  }, []);

  // Le handoff Spordateur se précharge au montage (mobile : pas de survol).
  useEffect(() => { if (etat === 'ok') prechargerSpordate(); }, [etat]);

  const passes = (me && Array.isArray(me.passes)) ? me.passes : [];
  const passAffiche = passes.find((p) => p && p.id === passAfficheId) || null;
  // Le pass qui porte le lien d'invitation : celui qu'on affiche s'il est
  // ouvert, sinon le pass courant (le plus récent des ouverts).
  const passLien = passAffiche && STATUTS_OUVERTS.indexOf(passAffiche.status) >= 0 ? passAffiche : passCourant(passes);
  // V538 : ce qu'on PARTAGE est la page d'apercu (`share_url`) — c'est
  // désormais l'assistant V551 qui la partage (WhatsApp, Partager, Copier, QR).
  const prenom = (me && me.sponsor && me.sponsor.first_name) || '';
  const initiale = prenom ? prenom.charAt(0).toUpperCase() : '';

  /** Remplace (ou ajoute) un pass dans l'état local depuis une réponse serveur. */
  const poserPass = useCallback((dto) => {
    if (!dto || !dto.id) return;
    setMe((prev) => {
      if (!prev) return prev;
      const liste = Array.isArray(prev.passes) ? prev.passes : [];
      const idx = liste.findIndex((p) => p && p.id === dto.id);
      const suivant = idx >= 0 ? liste.map((p, i) => (i === idx ? dto : p)) : [dto].concat(liste);
      return Object.assign({}, prev, { passes: suivant });
    });
    setPassAfficheId(dto.id);
  }, []);

  /** V538 — relit `/me` et repose les compteurs. Silencieux : un compteur pas
   *  rafraichi ne doit jamais casser l'ecran. */
  const rafraichirResultats = useCallback(() => (
    axios.get(`${API_PARRAINAGE}/me`, { headers: enteteParrain(), timeout: 10000 })
      .then((r) => {
        const d = (r && r.data) || {};
        if (d && d.stats) setMe((prev) => Object.assign({}, prev || {}, d));
      })
      .catch(() => { /* les compteurs se remettront au prochain chargement */ })
  ), []);

  /** Journalise une invitation ; met le pass en `waiting` s'il était `locked`. Silencieux en cas d'échec. */
  const journaliser = useCallback((pass, channel) => {
    if (!pass) return Promise.resolve();
    return axios.post(`${API_PARRAINAGE}/invitations`, { pass_id: pass.id, channel }, { headers: enteteParrain() })
      .then((r) => {
        const id = (r && r.data && r.data.id) || `local-${Date.now()}`;
        setMe((prev) => {
          if (!prev) return prev;
          const invitations = [{ id, pass_id: pass.id, channel, created_at: new Date().toISOString() }]
            .concat(Array.isArray(prev.invitations) ? prev.invitations : []);
          // V556 : la réponse porte le PROCHAIN `share_url` / `card_url` (version
          // d'aperçu incrémentée) — le prochain partage aura une URL neuve.
          const d = (r && r.data) || {};
          const neuf = {};
          if (typeof d.share_url === 'string' && d.share_url) neuf.share_url = d.share_url;
          if (typeof d.card_url === 'string' && d.card_url) neuf.card_url = d.card_url;
          const passes2 = (Array.isArray(prev.passes) ? prev.passes : []).map((p) => {
            if (!p || p.id !== pass.id) return p;
            const maj = Object.assign({}, neuf);
            if (p.status === 'locked') Object.assign(maj, { status: 'waiting', status_label: 'En attente de ton ami' });
            return Object.keys(maj).length ? Object.assign({}, p, maj) : p;
          });
          const stats = Object.assign({}, prev.stats || {}, { invited: (Number(prev.stats && prev.stats.invited) || 0) + 1 });
          return Object.assign({}, prev, { invitations, passes: passes2, stats });
        });
      })
      .catch(() => { /* le partage a eu lieu ; le journal n'est pas bloquant */ });
  }, []);

  /** V551 — le QR (action secondaire de l'assistant) : même lien, même journal. */
  const surQr = (pass, url) => {
    if (!pass || !url) return;
    setQrUrl(url);
    journaliser(pass, 'qr');
  };
  /** V551 — « Créer un nouveau Pass Duo » / « Préparer mon invitation » : l'assistant porte la création. */
  const preparerInvitation = () => {
    if (passLien) setCreationForcee(true);
    // V552 : appelé depuis le tiroir Pass Duo — on le ferme d'abord, puis on
    // amène l'assistant (toujours monté) à l'écran.
    setOutil('');
    setTimeout(() => {
      const cible = document.querySelector('[data-testid="invitation-zone"]');
      if (cible && cible.scrollIntoView) cible.scrollIntoView({ behavior: 'auto', block: 'start' });
    }, 0);
  };

  const creerPass = (course_id, occurrence, terms_accepted, offer_id) => {
    setOccupe(true); setErreurPass('');
    // V534: `terms_accepted` = la case ConditionsParticipation du formulaire (preuve T1 du parrain, jamais inventée)
    // V534b: `offer_id` = l'offre choisie dans la carte (le serveur la valide toujours ; null = serveur sans catalogue)
    const corps = { course_id, occurrence, terms_accepted: terms_accepted === true };
    if (offer_id) corps.offer_id = offer_id;
    axios.post(`${API_PARRAINAGE}/pass`, corps, { headers: enteteParrain() })
      .then((r) => {
        poserPass(r.data);
      })
      .catch((e) => {
        const s = e && e.response && e.response.status;
        const detail = String((e && e.response && e.response.data && e.response.data.detail) || '');
        setErreurPass(s === 400 && /^offre_/.test(detail)
          ? 'Cette offre n’est plus disponible pour cette séance. Choisis-en une autre.'
          : s === 400 ? 'Cette séance n’est pas ouverte au Pass Duo.'
            : s === 429 ? 'Trop de tentatives. Réessaie dans un instant.'
              : 'Création impossible pour le moment.');
      })
      .finally(() => setOccupe(false));
  };
  /**
   * V534b: `PATCH /pass/{id}/offer {offer_id, version}` — l'état local vient du PassDTO renvoyé.
   * 409 `conflit_version` → UN rechargement de /me (jamais en boucle), puis la carte réaffiche le
   * sélecteur avec le message ; 409 `pass_non_modifiable` → le `detail` du serveur.
   * Renvoie `{ok}` ou `{ok:false, conflit?, message}` à la carte (qui garde ou ferme son sheet).
   */
  const changerOffrePass = (id, offer_id, version) => {
    setOccupe(true); setErreurPass('');
    return changerOffre({ passId: id, offerId: offer_id, version, headers: enteteParrain() })
      .then((r) => { poserPass(r.data); return { ok: true }; })
      .catch((e) => {
        const refus = lireRefus(e);
        if (refus.status === 409 && refus.raison === 'conflit_version') {
          return axios.get(`${API_PARRAINAGE}/me`, { headers: enteteParrain(), timeout: 10000 })
            .then((r) => {
              const d = (r && r.data) || {};
              if (Array.isArray(d.passes)) setMe((prev) => Object.assign({}, prev || {}, d));
              return { ok: false, conflit: true, message: TEXTE_OFFRE_CONFLIT };
            })
            .catch(() => ({ ok: false, conflit: true, message: TEXTE_OFFRE_CONFLIT }));
        }
        const pass = passes.find((p) => p && p.id === id);
        return { ok: false, message: messageRefusOffre(refus, pass && pass.status) };
      })
      .finally(() => setOccupe(false));
  };
  const annulerPass = (id) => {
    setOccupe(true); setErreurPass('');
    axios.post(`${API_PARRAINAGE}/pass/${encodeURIComponent(id)}/cancel`, {}, { headers: enteteParrain() })
      // V538 : les compteurs du haut decrivent ce qui est EN COURS. Apres une
      // annulation ils ne peuvent pas rester sur les chiffres d'avant : on relit
      // `/me`, seule source de verite (l'historique, lui, ne bouge pas).
      .then((r) => { poserPass(r.data); return rafraichirResultats(); })
      .catch((e) => {
        const s = e && e.response && e.response.status;
        setErreurPass(s === 409 ? 'Ce Pass est déjà débloqué : annule depuis tes réservations.' : 'Annulation impossible pour le moment.');
      })
      .finally(() => setOccupe(false));
  };
  // V539b — LE PARRAIN CHANGE LA SÉANCE DE SON PASS.
  // Même route, même règle et même verrou de version que côté ami : le serveur
  // ne distingue que QUI appelle. En cas de conflit, on relit `/me` une fois,
  // comme pour le changement d'offre — jamais d'écrasement silencieux.
  const changerSeancePass = (id, occurrence, version) => {
    setOccupe(true); setErreurPass('');
    return changerSeance({ passId: id, occurrence, version, headers: enteteParrain() })
      .then((r) => { poserPass(r.data); return { ok: true }; })
      .catch((e) => {
        const refus = lireRefus(e);
        if (refus.status === 409 && refus.raison === 'conflit_version') {
          return axios.get(`${API_PARRAINAGE}/me`, { headers: enteteParrain(), timeout: 10000 })
            .then((r) => {
              const d = (r && r.data) || {};
              if (Array.isArray(d.passes)) setMe((prev) => Object.assign({}, prev || {}, d));
              return { ok: false, conflit: true, message: TEXTE_OFFRE_CONFLIT };
            })
            .catch(() => ({ ok: false, conflit: true, message: TEXTE_OFFRE_CONFLIT }));
        }
        return { ok: false, message: refus.detail || "Cette séance n'est plus disponible : choisis-en une autre." };
      })
      .finally(() => setOccupe(false));
  };

  const confirmerPass = (id, terms_accepted) => {
    setOccupe(true); setErreurPass('');
    // V534: la preuve T1 n'est envoyée que si la case a été cochée (jamais inventée)
    const corps = terms_accepted === true ? { terms_accepted: true } : {};
    axios.post(`${API_PARRAINAGE}/pass/${encodeURIComponent(id)}/confirm`, corps, { headers: enteteParrain() })
      .then((r) => poserPass(r.data))
      .catch((e) => {
        const s = e && e.response && e.response.status;
        const raison = e && e.response && e.response.headers && e.response.headers['x-refus-raison'];
        setErreurPass(s === 409 && raison === 'sponsor_sans_seance'
          ? 'Toujours aucune séance disponible : réserve ou recharge, puis confirme.'
          : s === 409 && raison === 'conditions_non_acceptees'
            ? 'Accepte les conditions de participation pour confirmer ta place.'
            : 'Confirmation impossible pour le moment.');
      })
      .finally(() => setOccupe(false));
  };

  // ── États de page ─────────────────────────────────────────────────────────
  if (etat === 'chargement') {
    return (
      <Cadre>
        <div className="cp-state" data-testid="centre-chargement">
          <div className="cp-spinner" aria-hidden="true" />
          <p className="cp-lead">Ton Parrainage arrive…</p>
        </div>
      </Cadre>
    );
  }
  if (etat === 'non_connecte') {
    return (
      <Cadre>
        <div className="cp-state" data-testid="centre-non-connecte">
          <div className="cp-roundic"><SvgIcon name="lock" size={38} /></div>
          <h1 className="cp-h1 cp-center">Ouvre ton espace abonné pour accéder à ton <em className="cp-em">Parrainage</em></h1>
          {urlEspace ? (
            <>
              <p className="cp-lead cp-center">Ta session t'attend : ouvre ton espace, puis reviens ici.</p>
              <a className="cp-b" href={urlEspace} data-testid="centre-vers-espace"><SvgIcon name="user" size={20} /> Ouvrir mon espace abonné</a>
            </>
          ) : (
            <>
              <p className="cp-lead cp-center">
                Ton espace abonné s'ouvre depuis le lien reçu par e-mail après ton inscription
                (afroboost.com/espace/TON-CODE). Le Parrainage y est réservé aux abonnés.
              </p>
              <a className="cp-b cp-b--ghost" href="/">Retour à l'accueil</a>
            </>
          )}
        </div>
      </Cadre>
    );
  }
  if (etat === 'desactive') {
    return (
      <Cadre>
        <div className="cp-state" data-testid="centre-desactive">
          <div className="cp-roundic"><SvgIcon name="gift" size={38} /></div>
          <h1 className="cp-h1 cp-center">Bientôt <em className="cp-em">disponible</em></h1>
          <p className="cp-lead cp-center">Le Parrainage Afroboost ouvre prochainement. Reviens bientôt.</p>
          <a className="cp-b cp-b--ghost" href={urlEspace || '/'}>{urlEspace ? 'Retour à mon espace' : "Retour à l'accueil"}</a>
        </div>
      </Cadre>
    );
  }
  if (etat === 'erreur') {
    return (
      <Cadre>
        <div className="cp-state" data-testid="centre-erreur">
          <div className="cp-roundic"><SvgIcon name="warning" size={38} /></div>
          <h1 className="cp-h1 cp-center">Impossible de charger ton Parrainage</h1>
          <p className="cp-lead cp-center">Vérifie ta connexion et recharge la page.</p>
          <button type="button" className="cp-b cp-b--ghost" onClick={() => window.location.reload()}>Recharger</button>
        </div>
      </Cadre>
    );
  }

  // ── Centre complet ────────────────────────────────────────────────────────
  const invitations = Array.isArray(me.invitations) ? me.invitations : [];
  // V534b: les lignes « Offre modifiée : A → B » viennent de history[] (type offer_changed), sinon des offer_history[]
  const history = lignesHistorique(me.history, passes);
  const parId = {};
  passes.forEach((p) => { if (p && p.id) parId[p.id] = p; });

  // V552 — le contenu COMPLET de chaque tiroir : les blocs d'avant, tels quels.
  const contenus = {
    credits: (
      <div className="cp-card" data-testid="programme-credits">
        <div className="cp-prog">
          <h3 className="cp-h3"><SvgIcon name="dollarSign" size={20} />Parrainage crédits</h3>
          <span className="cp-chip cp-chip--ext">Spordateur</span>
        </div>
        <p>1 crédit Sport Date par achat de ton filleul · jusqu'à 50 filleuls</p>
        <p className="cp-mini">Ton code, ton solde et tes filleuls restent gérés sur ton profil Spordateur.</p>
        <button type="button" className="cp-b cp-b--secondary" onClick={() => entrerDansSpordate('/profile')}
                onMouseEnter={prechargerSpordate} onFocus={prechargerSpordate} data-testid="programme-credits-gerer">
          <SvgIcon name="externalLink" size={20} /> Gérer mes crédits
        </button>
      </div>
    ),
    pass: (
      <>
        <PassDuoCard
          config={config}
          passes={passes}
          passAffiche={passAffiche}
          initialeParrain={initiale}
          urlEspace={urlEspace}
          onCreer={creerPass}
          onAnnuler={annulerPass}
          onConfirmer={confirmerPass}
          onChoisir={(id) => { setErreurPass(''); setPassAfficheId(id); }}
          onChangerOffre={changerOffrePass}
          onChangerSeance={changerSeancePass}
          onPreparerInvitation={preparerInvitation}
          occupe={occupe}
          erreur={erreurPass}
        />
      </>
    ),
    invitations: (
      <div className="cp-card cp-card--tight" data-testid="mes-invitations">
        {invitations.length === 0 ? (
          <p className="cp-empty">Aucune invitation pour l'instant. Partage ton lien pour commencer.</p>
        ) : invitations.map((inv, i) => {
          const p = parId[inv.pass_id];
          const ami = p && p.invitee && p.invitee.first_name;
          const offreInv = offreDuPass(p); // V534b: l'offre du pass, par son nom (jamais son id)
          return (
            <div className="cp-row" key={inv.id || i} data-testid="invitation-row">
              <div className="cp-who">
                <div className="cp-av-s">{ami ? ami.charAt(0).toUpperCase() : <SvgIcon name="user" size={16} />}</div>
                <div>
                  <b>{ami || 'Invitation'}</b>
                  <small>
                    {CANAUX[inv.channel] || inv.channel || 'Lien'}
                    {p && p.occurrence ? ` · Pass Duo ${libelleJour(p.occurrence).toLowerCase()}` : ''}
                    {offreInv ? ` · ${offreInv.name}` : ''}
                    {inv.created_at ? ` · ${libelleDateCourte(inv.created_at)}` : ''}
                  </small>
                </div>
              </div>
              {p ? <ChipStatut status={p.status} /> : <span className="cp-chip cp-chip--ext">Pass retiré</span>}
            </div>
          );
        })}
      </div>
    ),
    historique: (
      <div className="cp-card cp-card--list" data-testid="historique">
        {history.length === 0 ? (
          <p className="cp-empty">Ton historique se remplira au fil de tes invitations.</p>
        ) : (
          <ul className="cp-hist">
            {history.map((h, i) => (
              <li key={`${h.at || ''}-${i}`}><time>{libelleDateCourte(h.at)}</time><span>{h.label || h.type}</span></li>
            ))}
          </ul>
        )}
      </div>
    ),
  };
  const etats = etatsOutils({ passes, passLien, invitations, history });
  const outilOuvert = OUTILS.find((o) => o.id === outil) || null;

  return (
    <Cadre>
      <div className="cp-eyebrow">Mon centre{prenom ? ` · ${prenom}` : ''}</div>
      <h1 className="cp-h1 cp-h1--compact">Invite un ami, <em className="cp-em">profitez à deux.</em></h1>

      <div className="cp-stats cp-stats--compact" data-testid="mes-resultats" role="group" aria-label="Mes résultats">
        {libellesResultats(me.stats).map((s) => (
          <div className="cp-stat" key={s.testid} data-testid={s.testid}><b>{s.valeur}</b><span>{s.libelle}</span></div>
        ))}
      </div>

      {/* V551 — UNE SEULE ZONE D'INVITATION, JAMAIS DEUX FORMULAIRES.
          V552 : elle reste PRIORITAIRE et TOUJOURS MONTÉE — les tiroirs sont
          rendus à côté, jamais à sa place : son état survit à leur ouverture. */}
      <h2 className="cp-h2">Inviter un ami</h2>
      <div data-testid="invitation-zone">
        <InvitationWizard
          courses={config && config.courses}
          passOuvert={passLien}
          contexte={contexte}
          creationForcee={creationForcee}
          onRetour={() => setCreationForcee(false)}
          onPass={(dto) => { poserPass(dto); setCreationForcee(false); }}
          onJournal={journaliser}
          onQr={surQr}
        />
      </div>

      {/* V552 — MES OUTILS : quatre raccourcis compacts, un tiroir commun. */}
      <h2 className="cp-h2">Mes outils</h2>
      <div className="cp-outils" data-testid="mes-outils">
        {OUTILS.map((o) => (
          <button key={o.id} type="button" className="cp-outil" data-testid={`outil-${o.id}`}
                  ref={(el) => { declencheurs.current[o.id] = el; }}
                  aria-haspopup="dialog" aria-expanded={outil === o.id}
                  onClick={() => { setErreurPass(''); setOutil(o.id); }}>
            <span className="cp-outil-ic" aria-hidden="true"><SvgIcon name={o.icone} size={18} /></span>
            <span className="cp-outil-txt">
              <b>{o.titre}</b>
              <small>{etats[o.id]}</small>
            </span>
          </button>
        ))}
      </div>

      {outilOuvert ? (
        <ParrainageDrawer key={outilOuvert.id} titre={outilOuvert.titre} outil={outilOuvert.id}
                          declencheur={declencheurs.current[outilOuvert.id]} onClose={() => setOutil('')}>
          {contenus[outilOuvert.id]}
        </ParrainageDrawer>
      ) : null}

      {qrUrl ? <ModaleQr url={qrUrl} onClose={() => setQrUrl('')} /> : null}
    </Cadre>
  );
}

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
 * CE QU'ON N'AFFICHE PAS : « crédits Spordateur gagnés » — la donnée n'est
 * pas disponible proprement côté Afroboost ; la Carte 1 renvoie au profil
 * Spordateur, source de vérité, sans rien inventer.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { QRCodeCanvas } from 'qrcode.react';
import SvgIcon from '../SvgIcon';
import PassDuoCard, { ChipStatut } from './PassDuoCard';
import { entrerDansSpordate, prechargerSpordate } from '../../utils/spordateHandoff';
import {
  API_PARRAINAGE, enteteParrain, aUneIdentiteParrain, urlEspaceCourant, lireConfigParrainage,
  lienWhatsApp, copier, partager, passCourant, libelleJour, libelleDateCourte, STATUTS_OUVERTS,
  changerOffre, lireRefus, messageRefusOffre, lignesHistorique, offreDuPass, TEXTE_OFFRE_CONFLIT, // V534b
} from '../../utils/parrainage';
import './parrainage.css';

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
  const [feedback, setFeedback] = useState('');
  const [qrOuvert, setQrOuvert] = useState(false);
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

  // Le retour visuel (« Lien copié ») s'efface seul.
  useEffect(() => {
    if (!feedback) return undefined;
    const t = setTimeout(() => setFeedback(''), 2600);
    return () => clearTimeout(t);
  }, [feedback]);

  const passes = (me && Array.isArray(me.passes)) ? me.passes : [];
  const passAffiche = passes.find((p) => p && p.id === passAfficheId) || null;
  // Le pass qui porte le lien d'invitation : celui qu'on affiche s'il est
  // ouvert, sinon le pass courant (le plus récent des ouverts).
  const passLien = passAffiche && STATUTS_OUVERTS.indexOf(passAffiche.status) >= 0 ? passAffiche : passCourant(passes);
  // V538 : ce qu'on PARTAGE est la page d'apercu (`share_url`), qui redirige vers
  // l'invitation — c'est elle qui porte le prenom, la seance et l'image dans
  // WhatsApp. Repli sur `invite_url` si le serveur est anterieur a V538.
  const lienInvite = passLien ? (passLien.share_url || passLien.invite_url) : '';
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
          const passes2 = (Array.isArray(prev.passes) ? prev.passes : []).map((p) => (
            p && p.id === pass.id && p.status === 'locked'
              ? Object.assign({}, p, { status: 'waiting', status_label: 'En attente de ton ami' })
              : p
          ));
          const stats = Object.assign({}, prev.stats || {}, { invited: (Number(prev.stats && prev.stats.invited) || 0) + 1 });
          return Object.assign({}, prev, { invitations, passes: passes2, stats });
        });
      })
      .catch(() => { /* le partage a eu lieu ; le journal n'est pas bloquant */ });
  }, []);

  const surWhatsApp = () => {
    if (!passLien) return;
    const texte = passLien.whatsapp_text || `Rejoins mon Pass Duo Afroboost : ${lienInvite}`;
    window.open(lienWhatsApp(texte), '_blank', 'noopener');
    journaliser(passLien, 'whatsapp');
  };
  const surCopier = () => {
    if (!passLien) return;
    copier(lienInvite).then((ok) => {
      setFeedback(ok ? 'Lien copié' : 'Copie impossible : sélectionne le lien à la main');
      if (ok) journaliser(passLien, 'copy');
    });
  };
  const surQr = () => {
    if (!passLien) return;
    setQrOuvert(true);
    journaliser(passLien, 'qr');
  };
  const surPartager = () => {
    if (!passLien) return;
    partager({ title: 'Pass Duo Afroboost', text: passLien.whatsapp_text || '', url: lienInvite })
      .then((r) => {
        if (!r.ok) return;
        if (r.methode === 'copie') setFeedback('Lien copié');
        journaliser(passLien, r.methode === 'copie' ? 'copy' : 'share');
      });
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
        if (r.data && r.data.deja_existant) setFeedback('Tu as déjà un Pass Duo pour cette séance');
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

  return (
    <Cadre>
      <div className="cp-eyebrow">Mon centre{prenom ? ` · ${prenom}` : ''}</div>
      <h1 className="cp-h1">Invite un ami, <em className="cp-em">profitez à deux.</em></h1>
      <p className="cp-lead">Tes invitations, tes programmes et tes résultats, au même endroit.</p>

      <h2 className="cp-h2">Mes résultats</h2>
      <div className="cp-stats" data-testid="mes-resultats">
        {libellesResultats(me.stats).map((s) => (
          <div className="cp-stat" key={s.testid} data-testid={s.testid}><b>{s.valeur}</b><span>{s.libelle}</span></div>
        ))}
      </div>

      {/* V538 — DEUX ÉTATS, JAMAIS LES DEUX À LA FOIS.
          Sans Pass, quatre boutons de partage grisés ne disent pas quoi faire :
          la première action est d'en créer un, et c'est elle qu'on montre.
          Avec un Pass, l'écran devient ce qu'il doit être : inviter. */}
      {!lienInvite ? (
        <div className="cp-card" data-testid="creer-pass-cta">
          <h2 className="cp-h2" style={{ marginTop: 0 }}>Commence par ton Pass Duo</h2>
          <p className="cp-lead" style={{ marginTop: 0 }}>
            Choisis ta séance, crée ton Pass, puis invite ton ami en un geste.
          </p>
          <button type="button" className="cp-b" data-testid="creer-pass-bouton"
                  onClick={() => {
                    const cible = document.querySelector('[data-testid="pass-duo-card"]');
                    if (cible && cible.scrollIntoView) cible.scrollIntoView({ behavior: 'auto', block: 'center' });
                  }}>
            <SvgIcon name="plus" size={20} /> Créer mon Pass Duo
          </button>
        </div>
      ) : null}

      <h2 className="cp-h2">{lienInvite ? 'Inviter un ami' : 'Inviter un ami (après ton Pass)'}</h2>
      <div className="cp-card" data-testid="inviter-un-ami">
        <div className={`cp-code${lienInvite ? '' : ' cp-code--off'}`}>
          <div>
            <small>Mon lien d'invitation</small>
            {lienInvite ? lienAffiche(lienInvite) : 'Crée ton Pass Duo ci-dessous'}
          </div>
          {lienInvite ? (
            <button type="button" className="cp-iconbtn" onClick={surCopier} aria-label="Copier le lien" data-testid="inviter-copier-icone">
              <SvgIcon name="copy" size={22} />
            </button>
          ) : <SvgIcon name="lock" size={22} />}
        </div>
        <div className="cp-share">
          <button type="button" className="cp-b cp-b--whatsapp" onClick={surWhatsApp} disabled={!lienInvite} data-testid="inviter-whatsapp">
            <SvgIcon name="send" size={20} />WhatsApp
          </button>
          <button type="button" className="cp-b cp-b--secondary" onClick={surCopier} disabled={!lienInvite} data-testid="inviter-copier">
            <SvgIcon name="copy" size={20} />Copier
          </button>
          <button type="button" className="cp-b cp-b--secondary" onClick={surQr} disabled={!lienInvite} data-testid="inviter-qr">
            <SvgIcon name="qrCode" size={20} />QR
          </button>
          <button type="button" className="cp-b cp-b--secondary" onClick={surPartager} disabled={!lienInvite} data-testid="inviter-partager">
            <SvgIcon name="share" size={20} />Partager
          </button>
        </div>
        {feedback ? <p className="cp-ok-text" role="status" data-testid="inviter-feedback">{feedback}</p> : null}
        <p className="cp-mini">
          {lienInvite
            ? "Ton ami profite d'un essai gratuit. Le lien ne contient jamais ton e-mail."
            : 'Les boutons s’activent dès que tu as créé un Pass Duo pour une séance.'}
        </p>
      </div>

      <h2 className="cp-h2">Mes programmes</h2>
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
        occupe={occupe}
        erreur={erreurPass}
      />

      <h2 className="cp-h2">Mes invitations</h2>
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

      <h2 className="cp-h2">Historique</h2>
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

      {qrOuvert && lienInvite ? <ModaleQr url={lienInvite} onClose={() => setQrOuvert(false)} /> : null}
    </Cadre>
  );
}

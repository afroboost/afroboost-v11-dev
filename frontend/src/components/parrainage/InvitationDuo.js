/**
 * V534 — INVITATION PUBLIQUE (page /duo/<token>).
 *
 * L'ami ouvre le lien du parrain : « Invitation de <prénom> », le VRAI cours,
 * sa date, son heure, son lieu (+ itinéraire), puis un formulaire court —
 * Prénom / E-mail / WhatsApp / consentement réservation (obligatoire) / offres
 * (facultatif, JAMAIS pré-coché) — et « M'inscrire et débloquer le duo ».
 *
 * RÉSEAU : `GET /api/referral/pass/{token}` au montage (public, aucun e-mail ni
 * téléphone dans la réponse). Si un abonné est identifié côté navigateur, UN
 * `GET /me` supplémentaire sert à reconnaître son propre lien (« C'est ton
 * lien : partage-le à un ami ») — jamais de sondage.
 *
 * REFUS : 409 lus dans l'en-tête `X-Refus-Raison` → messages FR précis ; 410 →
 * « Cette invitation a expiré » ; 404 → « Invitation introuvable » ; drapeau
 * OFF → « Invitation indisponible ».
 *
 * V534b — L'OFFRE : `GET /pass/{token}` porte `offer` (celle du pass), `offers`
 * (le catalogue courant du cours) et `version`. Entre la séance et le
 * formulaire : « OFFRE — nom / avantage / Offerte » + [Cette offre me convient]
 * (déplie le formulaire) + [Voir les autres offres] (absent si une seule offre)
 * → même sélecteur (bottom sheet) → `PATCH /pass/{token}/offer {offer_id,
 * version}` (public, avant inscription) → puis le formulaire. Après
 * l'inscription, l'ami ne change plus rien : seul le parrain le peut.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';
import BilletsDuo from './BilletsDuo';
import { EncartOffre, SheetOffres } from './OffresDuo'; // V534b
import { attributionActuelle } from '../../utils/attribution';
import {
  API_PARRAINAGE, enteteParrain, aUneIdentiteParrain, libelleJour, libelleHeure,
  messageRefus, messageErreurInvitation,
  offreDuPass, offresDe, changerOffre, lireRefus, messageRefusOffre, TEXTE_OFFRE_CONFLIT, // V534b
} from '../../utils/parrainage';
import './parrainage.css';

/** Le message pour un GET /pass/{token} qui n'a pas abouti (ou un pass fermé). */
export function messageInvitationDepuisReponse(status, detail) {
  if (status === 404 && String(detail || '') === 'parrainage_duo_desactive') return 'Invitation indisponible';
  return messageErreurInvitation(status);
}

function Cadre({ children }) {
  return (
    <div className="cp-root cp-page" data-testid="invitation-duo">
      <main className="cp-app">
        <header className="cp-header">
          <a className="cp-logo" href="/" aria-label="Afroboost">Afro<span>boost</span></a>
          <div className="cp-pill">Pass Duo</div>
        </header>
        {children}
        <footer className="cp-footer">Danse · Fitness · Good vibes</footer>
      </main>
    </div>
  );
}

function CarteSeance({ course, occurrence }) {
  const c = course || {};
  const jour = libelleJour(occurrence);
  const heure = libelleHeure(occurrence);
  return (
    <div className="cp-card" data-testid="invitation-seance">
      <div className="cp-hero">
        <div>
          <b>{c.name || 'Séance Afroboost'}</b>
          <small>Cardio-danse afrobeat · Avec casques · Accessible à tous</small>
        </div>
      </div>
      <h3 className="cp-h3" style={{ marginTop: 16 }}>
        <SvgIcon name="calendar" size={20} />
        {jour}{heure ? ` · ${heure}` : (c.time ? ` · ${c.time}` : '')}
      </h3>
      {c.locationName ? (
        <p style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <SvgIcon name="mapPin" size={16} /> {c.locationName}
          {c.mapsUrl && /^https?:\/\//i.test(c.mapsUrl) ? (
            <a className="cp-link" href={c.mapsUrl} target="_blank" rel="noopener noreferrer" data-testid="invitation-itineraire">
              Itinéraire <SvgIcon name="externalLink" size={14} />
            </a>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}

function EcranMessage({ titre, texte, icone }) {
  return (
    <div className="cp-state">
      <div className="cp-roundic"><SvgIcon name={icone || 'warning'} size={38} /></div>
      <h1 className="cp-h1 cp-center">{titre}</h1>
      {texte ? <p className="cp-lead cp-center">{texte}</p> : null}
      <a className="cp-b cp-b--ghost" href="/">Découvrir Afroboost</a>
    </div>
  );
}

export default function InvitationDuo({ token }) {
  const [etat, setEtat] = useState('chargement'); // chargement | ok | message
  const [message, setMessage] = useState('');
  const [pass, setPass] = useState(null);
  const [monLien, setMonLien] = useState(false);
  const [form, setForm] = useState({ name: '', email: '', whatsapp: '', consent: false, marketing: false });
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState('');
  const [resultat, setResultat] = useState(null); // {status, tickets, blocked_reason}
  // V534b: l'offre — le formulaire ne se déplie qu'après « Cette offre me convient »
  const [offreOk, setOffreOk] = useState(false);
  const [sheetOffre, setSheetOffre] = useState(false);
  const [offreOccupe, setOffreOccupe] = useState(false);
  const [offreMessage, setOffreMessage] = useState('');
  const [offreErreur, setOffreErreur] = useState('');

  useEffect(() => {
    let vivant = true;
    if (!token) { setMessage('Invitation introuvable'); setEtat('message'); return undefined; }
    axios.get(`${API_PARRAINAGE}/pass/${encodeURIComponent(token)}`, { timeout: 10000 })
      .then((r) => {
        if (!vivant) return;
        const d = (r && r.data) || {};
        if (d.enabled === false) { setMessage('Invitation indisponible'); setEtat('message'); return; }
        if (d.expired || d.status === 'expired') { setMessage('Cette invitation a expiré'); setEtat('message'); return; }
        if (d.status === 'cancelled') { setMessage("Ce Pass Duo n'est plus ouvert."); setEtat('message'); return; }
        setPass(d);
        setEtat('ok');
      })
      .catch((e) => {
        if (!vivant) return;
        const s = e && e.response && e.response.status;
        const detail = e && e.response && e.response.data && e.response.data.detail;
        setMessage(messageInvitationDepuisReponse(s, detail));
        setEtat('message');
      });
    return () => { vivant = false; };
  }, [token]);

  // Son propre lien ? Un seul GET /me, seulement si une identité existe.
  useEffect(() => {
    let vivant = true;
    if (etat !== 'ok' || !aUneIdentiteParrain()) return undefined;
    axios.get(`${API_PARRAINAGE}/me`, { headers: enteteParrain(), timeout: 8000 })
      .then((r) => {
        if (!vivant) return;
        const passes = (r && r.data && Array.isArray(r.data.passes)) ? r.data.passes : [];
        const mien = passes.some((p) => p && p.share_token === token);
        setMonLien((prev) => (prev === mien ? prev : mien));
      })
      .catch(() => { /* pas abonné, ou pas le sien : rien à dire */ });
    return () => { vivant = false; };
  }, [etat, token]);

  // V534b: le choix de l'ami part par le PATCH public, avec la `version` du pass ;
  // 409 conflit_version → UN rechargement de GET /pass/{token}, puis le sélecteur
  // se réaffiche avec le message ; 409 pass_deja_rejoint / 400 → message précis.
  const choisirOffre = (offerId) => {
    if (!pass || offreOccupe) return;
    setOffreOccupe(true); setOffreErreur('');
    changerOffre({ token, offerId, version: pass.version })
      .then((r) => {
        const d = (r && r.data) || {};
        setPass((prev) => Object.assign({}, prev || {}, d.offer ? d : {
          offer: offresDe(prev).find((o) => String(o.id) === String(offerId)) || (prev && prev.offer),
          version: Number(prev && prev.version) + 1 || 1,
        }));
        setOffreMessage(''); setSheetOffre(false); setOffreOk(true);
      })
      .catch((e) => {
        const refus = lireRefus(e);
        if (refus.status === 409 && refus.raison === 'conflit_version') {
          return axios.get(`${API_PARRAINAGE}/pass/${encodeURIComponent(token)}`, { timeout: 10000 })
            .then((r) => { const d = (r && r.data) || {}; setPass((prev) => Object.assign({}, prev || {}, d)); })
            .catch(() => { /* on garde l'état connu */ })
            .then(() => { setOffreMessage(TEXTE_OFFRE_CONFLIT); });
        }
        setOffreErreur(messageRefusOffre(refus));
        return undefined;
      })
      .finally(() => setOffreOccupe(false));
  };

  const champ = (k) => (e) => {
    const v = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setForm((prev) => (prev[k] === v ? prev : Object.assign({}, prev, { [k]: v })));
  };

  const soumettre = (e) => {
    e.preventDefault();
    if (envoi) return;
    const name = form.name.trim();
    const email = form.email.trim().toLowerCase();
    const whatsapp = form.whatsapp.trim();
    if (!name) { setErreur('Indique ton prénom.'); return; }
    if (!email || email.indexOf('@') < 1) { setErreur('Indique une adresse e-mail valide.'); return; }
    if (!whatsapp) { setErreur('Indique ton numéro WhatsApp.'); return; }
    if (!form.consent) { setErreur('Coche la case liée à la réservation pour continuer.'); return; }
    setErreur(''); setEnvoi(true);
    let attribution = null;
    try { attribution = attributionActuelle(); } catch (x) { attribution = null; }
    const corps = {
      name, email, whatsapp,
      consent_reservation: true, terms_accepted: true, marketing_consent: !!form.marketing,
    };
    if (attribution) corps.attribution = attribution;
    axios.post(`${API_PARRAINAGE}/pass/${encodeURIComponent(token)}/join`, corps, { timeout: 20000 })
      .then((r) => { setResultat((r && r.data) || { status: 'unlocked', tickets: [] }); })
      .catch((err) => {
        const s = err && err.response && err.response.status;
        const h = (err && err.response && err.response.headers) || {};
        const raison = h['x-refus-raison'] || h['X-Refus-Raison'];
        if (s === 409) setErreur(messageRefus(raison));
        else if (s === 410) setErreur('Cette invitation a expiré');
        else if (s === 404) setErreur(messageInvitationDepuisReponse(404, err.response.data && err.response.data.detail));
        else if (s === 429) setErreur('Trop de tentatives. Réessaie dans un instant.');
        else if (s === 400 || s === 422) setErreur('Vérifie les champs du formulaire.');
        else setErreur('Inscription impossible pour le moment. Réessaie dans un instant.');
      })
      .finally(() => setEnvoi(false));
  };

  if (etat === 'chargement') {
    return (
      <Cadre>
        <div className="cp-state" data-testid="invitation-chargement">
          <div className="cp-spinner" aria-hidden="true" />
          <p className="cp-lead">On ouvre ton invitation…</p>
        </div>
      </Cadre>
    );
  }
  if (etat === 'message') {
    return (
      <Cadre>
        <div data-testid="invitation-message"><EcranMessage titre={message} icone={message.indexOf('expir') >= 0 ? 'clock' : 'warning'} /></div>
      </Cadre>
    );
  }

  const prenom = pass.sponsor_first_name || 'ton ami';

  // ── Succès ────────────────────────────────────────────────────────────────
  if (resultat) {
    const attente = resultat.status === 'friend_registered';
    return (
      <Cadre>
        <div className="cp-state" style={{ paddingTop: 10 }} data-testid={attente ? 'invitation-succes-attente' : 'invitation-succes'}>
          <div className={`cp-roundic${attente ? '' : ' cp-roundic--ok'}`}>
            <SvgIcon name={attente ? 'hourglass' : 'check'} size={38} strokeWidth="2.5" />
          </div>
          <h1 className="cp-h1 cp-center">
            {attente ? <>Inscription <em className="cp-em">confirmée</em></> : <>Votre Pass Duo est <em className="cp-em">débloqué</em></>}
          </h1>
          <div className="cp-avatars" aria-hidden="true">
            <div className="cp-av">{prenom.charAt(0).toUpperCase()}<small>{prenom}</small></div>
            <i />
            <div className={`cp-av${attente ? '' : ' cp-av--ok'}`}>{form.name.trim().charAt(0).toUpperCase() || '?'}<small>{form.name.trim() || 'Toi'}</small></div>
          </div>
          <p className="cp-center">
            {attente ? `Ta place est réservée. ${prenom} confirme la sienne, et vous serez deux.` : 'Vous avez chacun votre billet pour la même séance.'}
          </p>
        </div>
        <CarteSeance course={pass.course} occurrence={pass.occurrence} />
        {offreDuPass(resultat) || offreDuPass(pass) ? (
          <EncartOffre titre="Ton offre" offre={offreDuPass(resultat) || offreDuPass(pass)} testid="offre-recue" />
        ) : null}
        <BilletsDuo tickets={resultat.tickets} />
        <p className="cp-center cp-fine">Tu recevras aussi ton billet par e-mail.</p>
      </Cadre>
    );
  }

  // ── Invitation + formulaire ───────────────────────────────────────────────
  const dejaRejoint = pass.status === 'friend_registered' || pass.status === 'unlocked' || pass.status === 'used';
  // V534b: l'offre du pass et son catalogue. Sans `offer` (serveur antérieur) : formulaire direct, comme avant.
  const offre = offreDuPass(pass);
  const offres = offresDe(pass);
  const plusieursOffres = offres.length > 1;
  const formulaireVisible = !offre || offreOk || dejaRejoint;
  return (
    <Cadre>
      <div className="cp-eyebrow" data-testid="invitation-de">Invitation de {prenom}</div>
      <h1 className="cp-h1">Rejoins son <em className="cp-em">Pass Duo</em></h1>
      <p className="cp-lead">{offre ? 'Ton offre est débloquée dès ton inscription.' : 'Ton essai gratuit est débloqué dès ton inscription.'}</p>

      {monLien ? (
        <div className="cp-notice" data-testid="invitation-mon-lien">
          C'est ton lien : partage-le à un ami. <a className="cp-link" href="/parrainage">Voir mon Parrainage <SvgIcon name="arrowRight" size={14} /></a>
        </div>
      ) : null}

      <CarteSeance course={pass.course} occurrence={pass.occurrence} />

      {offre ? (
        <EncartOffre titre="Offre" offre={offre} testid="invitation-offre"
                     note={dejaRejoint ? null : `${prenom} t'offre cette offre : tu la reçois à ton inscription.`}>
          {!dejaRejoint && !offreOk ? (
            <div className="cp-offre-actions">
              <button type="button" className="cp-b" onClick={() => setOffreOk(true)} data-testid="offre-convient">
                <SvgIcon name="check" size={20} /> Cette offre me convient
              </button>
              {plusieursOffres ? (
                <button type="button" className="cp-b cp-b--ghost" onClick={() => { setOffreMessage(''); setOffreErreur(''); setSheetOffre(true); }} data-testid="offre-voir-autres">
                  <SvgIcon name="layers" size={20} /> Voir les autres offres
                </button>
              ) : null}
            </div>
          ) : null}
          {!dejaRejoint && offreOk && plusieursOffres ? (
            <button type="button" className="cp-link cp-offre-lien" onClick={() => { setOffreMessage(''); setOffreErreur(''); setSheetOffre(true); }} data-testid="offre-voir-autres">
              <SvgIcon name="refresh" size={14} /> Voir les autres offres
            </button>
          ) : null}
          {offreErreur && !sheetOffre ? <p className="cp-error" role="alert" data-testid="offre-erreur">{offreErreur}</p> : null}
        </EncartOffre>
      ) : null}

      {sheetOffre ? (
        <SheetOffres offres={offres} actuelleId={offre ? offre.id : null} onChoisir={choisirOffre}
                     onFermer={() => setSheetOffre(false)} occupe={offreOccupe} message={offreMessage} erreur={offreErreur}
                     titre="Choisis ton offre" name="cp-invitation-offre" />
      ) : null}

      {dejaRejoint ? (
        <div className="cp-notice" data-testid="invitation-deja-rejoint">
          Un ami a déjà rejoint ce Pass Duo. Si c'est toi, saisis les mêmes coordonnées pour retrouver ton billet.
        </div>
      ) : null}

      {formulaireVisible ? (
      <form onSubmit={soumettre} noValidate data-testid="invitation-form">
        <input className="cp-input" placeholder="Prénom" value={form.name} onChange={champ('name')} autoComplete="given-name" required data-testid="invitation-prenom" />
        <input className="cp-input" type="email" placeholder="E-mail" value={form.email} onChange={champ('email')} autoComplete="email" required data-testid="invitation-email" />
        <input className="cp-input" type="tel" placeholder="Numéro WhatsApp" value={form.whatsapp} onChange={champ('whatsapp')} autoComplete="tel" required data-testid="invitation-whatsapp" />
        <label className="cp-chk">
          <input type="checkbox" checked={form.consent} onChange={champ('consent')} required data-testid="invitation-consent" />
          <span>J'accepte de recevoir les informations liées à cette réservation (obligatoire).</span>
        </label>
        <label className="cp-chk">
          <input type="checkbox" checked={form.marketing} onChange={champ('marketing')} data-testid="invitation-marketing" />
          <span>Je souhaite recevoir les prochaines offres Afroboost (facultatif).</span>
        </label>
        {erreur ? <p className="cp-error" role="alert" data-testid="invitation-erreur">{erreur}</p> : null}
        <button type="submit" className="cp-b" disabled={envoi} data-testid="invitation-rejoindre">
          <SvgIcon name="users" size={20} /> {envoi ? 'Inscription…' : "M'inscrire et débloquer le duo"}
        </button>
      </form>
      ) : null}
      <p className="cp-fine cp-center" style={{ marginTop: 14 }}>
        Une seule invitation par personne et par séance. L'essai gratuit Afroboost est unique : si tu l'as déjà utilisé, on te le dira ici.
      </p>
    </Cadre>
  );
}

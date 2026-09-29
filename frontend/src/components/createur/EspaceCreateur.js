/**
 * V559 — ESPACE CRÉATEUR : le parcours complet autour du Dashboard Créateur,
 * le MÊME pour un abonné et pour un coach / partenaire.
 *
 *   statut none / rejected → « Devenir créateur » (principe, barème, règlement,
 *                            formulaire minimal, « Envoyer ma demande ») ;
 *   pending                → « Ta demande est en cours d'examen » ;
 *   suspended              → message, aucun lien ;
 *   approved               → CreatorDashboard.
 *
 * Aucun statut n'est décidé ici : le serveur (et la seule super-admin) tranche.
 *
 * RÉSEAU : UNE lecture au montage (GET /api/createur/me), jamais relancée par
 * un objet ; ensuite uniquement sur geste (demande, retrait).
 *
 * @param {function} entetes  () => en-têtes d'identité (espace abonné) ; absent
 *                            pour un coach (l'intercepteur pose le JWT).
 * @param {function} onStatut (statut) → prévient le parent (libellé du menu).
 */
import React, { useEffect, useRef, useState } from 'react';
import SvgIcon from '../SvgIcon';
import CreatorDashboard from './CreatorDashboard';
import {
  lireCreateur, envoyerDemandeCreateur, demanderRetrait, messageErreurCreateur,
} from '../../utils/createur';
import './createur.css';

const FORM_VIDE = { prenom: '', nom: '', telephone: '', email: '', reseaux: '', motivation: '',
  payout_method: 'twint', payout_detail: '', reglement_accepte: false };

export function DevenirCreateur({ info, onEnvoye, entetes, refus }) {
  const [form, setForm] = useState(FORM_VIDE);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState('');
  const champ = (cle) => (e) => {
    const v = e.target.type === 'checkbox' ? !!e.target.checked : e.target.value;
    setForm((prev) => (prev[cle] === v ? prev : Object.assign({}, prev, { [cle]: v })));
  };
  const commissions = (info && Array.isArray(info.commissions)) ? info.commissions : [];
  const soumettre = (e) => {
    e.preventDefault();
    if (envoi) return;
    if (!form.prenom.trim() || !form.nom.trim()) { setErreur('Indique ton prénom et ton nom.'); return; }
    if (!form.telephone.trim()) { setErreur('Indique ton numéro de téléphone.'); return; }
    if (!form.motivation.trim()) { setErreur('Parle-nous de ton activité ou de ta motivation.'); return; }
    if (form.payout_method === 'iban' && !form.payout_detail.trim()) { setErreur('Indique ton IBAN.'); return; }
    if (!form.reglement_accepte) { setErreur('Merci d’accepter le règlement du programme.'); return; }
    setErreur(''); setEnvoi(true);
    const corps = Object.assign({}, form);
    delete corps.email; // l'e-mail vient de ton identité, jamais du formulaire
    envoyerDemandeCreateur(corps, entetes)
      .then((d) => { if (typeof onEnvoye === 'function') onEnvoye(d); })
      .catch((err) => setErreur(messageErreurCreateur(err, 'Ta demande n’a pas pu être envoyée. Réessaie dans un instant.')))
      .finally(() => setEnvoi(false));
  };
  return (
    <div className="cr-root" data-testid="devenir-createur">
      <header className="cr-entete">
        <h2 className="cr-titre">Devenir créateur Afroboost</h2>
        <p className="cr-sous">Recommande Afroboost à ton réseau et gagne une commission sur les achats éligibles réalisés grâce à ton lien personnel.</p>
      </header>
      {refus ? <p className="cr-erreur" role="status" data-testid="cr-demande-refusee">Ta précédente demande n’a pas été retenue. Tu peux en envoyer une nouvelle.</p> : null}
      <section className="cr-carte" data-testid="cr-principe">
        <h3 className="cr-h3">Le principe</h3>
        <ul className="cr-puces">
          <li>Tu reçois un lien personnel et un QR code à partager.</li>
          <li>Quand une personne achète une offre éligible grâce à ton lien, tu gagnes une commission.</li>
          <li>Seuls les achats payés comptent : ni les clics, ni les inscriptions, ni les essais gratuits.</li>
          <li>Une commission est confirmée après {info && info.delai_confirmation_jours ? info.delai_confirmation_jours : 14} jours (délai de remboursement), puis tu peux demander un retrait dès {info && info.retrait_min ? info.retrait_min : 10} CHF.</li>
          <li>Tu touches la commission sur TES filleuls directs uniquement : jamais de commission en cascade.</li>
        </ul>
        <p className="cr-fine" data-testid="cr-bareme">
          {commissions.length ? <>Taux actuels : {commissions.join(' · ')}</> : 'Les taux de commission sont communiqués à l’approbation.'}
        </p>
      </section>
      <form className="cr-carte cr-form" onSubmit={soumettre} noValidate data-testid="cr-form">
        <h3 className="cr-h3">Ma demande</h3>
        <div className="cr-2col">
          <label className="cr-label">Prénom<input className="cr-input" value={form.prenom} onChange={champ('prenom')} maxLength={60} autoComplete="given-name" data-testid="cr-prenom" /></label>
          <label className="cr-label">Nom<input className="cr-input" value={form.nom} onChange={champ('nom')} maxLength={60} autoComplete="family-name" data-testid="cr-nom" /></label>
        </div>
        <label className="cr-label">Téléphone<input className="cr-input" type="tel" inputMode="tel" value={form.telephone} onChange={champ('telephone')} placeholder="+41 79 123 45 67" autoComplete="tel" data-testid="cr-telephone" /></label>
        <p className="cr-fine">Ton e-mail est celui de ton compte : tu n’as pas à le saisir.</p>
        <label className="cr-label">Réseaux sociaux (facultatif)<input className="cr-input" value={form.reseaux} onChange={champ('reseaux')} maxLength={200} placeholder="@instagram, TikTok…" data-testid="cr-reseaux" /></label>
        <label className="cr-label">Motivation / activité<textarea className="cr-input" rows={3} value={form.motivation} onChange={champ('motivation')} maxLength={600} data-testid="cr-motivation" /></label>
        <span className="cr-label">Méthode de paiement souhaitée</span>
        <div className="cr-choix" role="radiogroup" aria-label="Méthode de paiement">
          {[['twint', 'TWINT'], ['iban', 'IBAN (virement)']].map(([v, l]) => (
            <label key={v} className={`cr-radio${form.payout_method === v ? ' on' : ''}`}>
              <input type="radio" name="cr-methode" value={v} checked={form.payout_method === v} onChange={champ('payout_method')} data-testid={`cr-methode-${v}`} /> {l}
            </label>
          ))}
        </div>
        {form.payout_method === 'iban' ? (
          <label className="cr-label">IBAN<input className="cr-input" value={form.payout_detail} onChange={champ('payout_detail')} placeholder="CH93 0076 2011 6238 5295 7" autoComplete="off" data-testid="cr-iban" /></label>
        ) : (
          <label className="cr-label">Numéro TWINT (facultatif, sinon ton téléphone)<input className="cr-input" type="tel" value={form.payout_detail} onChange={champ('payout_detail')} data-testid="cr-twint" /></label>
        )}
        <label className="cr-chk">
          <input type="checkbox" checked={form.reglement_accepte} onChange={champ('reglement_accepte')} data-testid="cr-reglement" />
          <span>J’accepte le règlement du programme Créateur : commissions sur achats payés éligibles, confirmées après le délai de remboursement, versées manuellement par Afroboost ; aucune commission en cascade ; l’essai gratuit reste unique par personne.</span>
        </label>
        {erreur ? <p className="cr-erreur" role="alert" data-testid="cr-form-erreur">{erreur}</p> : null}
        <button type="submit" className="cr-b cr-b--plein cr-b--grand" disabled={envoi} data-testid="cr-envoyer">
          <SvgIcon name="send" size={18} /> {envoi ? 'Envoi…' : 'Envoyer ma demande'}
        </button>
      </form>
    </div>
  );
}

export default function EspaceCreateur({ entetes, onStatut }) {
  const [info, setInfo] = useState(null);
  const [erreur, setErreur] = useState('');
  const [retraitOccupe, setRetraitOccupe] = useState(false);
  const [retraitMessage, setRetraitMessage] = useState('');
  const [retraitErreur, setRetraitErreur] = useState('');
  const entetesRef = useRef(entetes);
  entetesRef.current = entetes;
  const onStatutRef = useRef(onStatut);
  onStatutRef.current = onStatut;

  const poser = (d) => {
    setInfo(d || null);
    if (d && typeof onStatutRef.current === 'function') onStatutRef.current(d.statut);
  };

  useEffect(() => {
    let vivant = true;
    lireCreateur(entetesRef.current)
      .then((d) => { if (vivant) poser(d); })
      .catch((err) => { if (vivant) setErreur(messageErreurCreateur(err, 'Ton espace créateur ne se charge pas pour le moment.')); });
    return () => { vivant = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const surRetrait = () => {
    if (retraitOccupe) return;
    setRetraitOccupe(true); setRetraitMessage(''); setRetraitErreur('');
    demanderRetrait(entetesRef.current)
      .then((d) => { poser(d); setRetraitMessage('Demande envoyée : Afroboost te paie manuellement après vérification.'); })
      .catch((err) => setRetraitErreur(messageErreurCreateur(err)))
      .finally(() => setRetraitOccupe(false));
  };

  if (erreur) return <p className="cr-erreur" role="alert" data-testid="cr-erreur">{erreur}</p>;
  if (!info) {
    return (
      <p className="cr-fine cr-chargement" role="status" data-testid="cr-chargement">
        <span className="cp-spinner" aria-hidden="true" /> Chargement de ton espace créateur…
      </p>
    );
  }
  if (info.statut === 'approved' && info.dashboard) {
    return (
      <CreatorDashboard data={info.dashboard} onRetrait={surRetrait} retraitOccupe={retraitOccupe}
                        retraitMessage={retraitMessage} retraitErreur={retraitErreur} />
    );
  }
  if (info.statut === 'pending') {
    return (
      <div className="cr-root" data-testid="cr-en-attente">
        <section className="cr-carte cr-centre">
          <span className="cr-rond"><SvgIcon name="hourglass" size={22} /></span>
          <h2 className="cr-titre">Demande envoyée</h2>
          <p className="cr-sous">Ta demande pour devenir créateur Afroboost est en cours d’examen. Ton Dashboard Créateur s’activera dès son approbation.</p>
        </section>
      </div>
    );
  }
  if (info.statut === 'suspended') {
    return (
      <div className="cr-root" data-testid="cr-suspendu">
        <section className="cr-carte cr-centre">
          <h2 className="cr-titre">Compte créateur suspendu</h2>
          <p className="cr-sous">Ton lien créateur est désactivé pour le moment. Contacte Afroboost pour en savoir plus.</p>
        </section>
      </div>
    );
  }
  return <DevenirCreateur info={info} entetes={entetesRef.current} refus={info.statut === 'rejected'} onEnvoye={poser} />;
}

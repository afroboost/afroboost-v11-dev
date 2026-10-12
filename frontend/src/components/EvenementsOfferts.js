/**
 * V610 — « TA PLACE OFFERTE » DANS L'ESPACE (membres avec abonnement 8 mois actif).
 *
 * La liste vient du SERVEUR (`evenements_offerts` de GET /subscriber/space) : il a
 * déjà vérifié l'abonnement de CETTE personne (e-mail de la session d'espace) à la
 * date de l'événement. Ici, aucun calcul de droit — un clic, une réservation à
 * 0 CHF (POST …/evenement/<offre>/offert, idempotent), puis le lien personnel pour
 * inviter (facultatif). Aucun paiement, aucun Stripe.
 */
import React, { useState } from 'react';
import axios from 'axios';
import SvgIcon from './SvgIcon';
import InviterMesAmis from './InviterMesAmis';
import { invitationActuelle } from '../utils/attribution';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;
const JOURS = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'];
const MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'];

/** « mercredi 28 octobre · 18h45 » depuis « 2026-10-28T18:45:00 » (heure de Zurich). */
export function quandEvenement(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(String(iso || ''));
  if (!m) return '';
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 12, 0, 0);
  return `${JOURS[d.getDay()]} ${d.getDate()} ${MOIS[d.getMonth()]} · ${Number(m[4])}h${m[5]}`;
}

function CarteEvenement({ evt, accessCode, memberSlug }) {
  const [etat, setEtat] = useState(evt.deja_reserve ? 'reservee' : 'libre');
  const [relais, setRelais] = useState(null);
  const [erreur, setErreur] = useState('');

  const reserver = async () => {
    if (etat === 'envoi') return;
    const avant = etat;
    setEtat('envoi');
    setErreur('');
    try {
      const inv = invitationActuelle();
      const r = await axios.post(
        `${BACKEND_URL}/api/subscriber/space/${encodeURIComponent(accessCode)}/evenement/${encodeURIComponent(evt.offer_id)}/offert`,
        { member_slug: memberSlug || undefined, jeton_invitation: inv ? inv.t : undefined });
      setRelais((r && r.data && r.data.relais) || null);
      setEtat('reservee');
    } catch (e) {
      const detail = e && e.response && e.response.data && e.response.data.detail;
      setErreur(typeof detail === 'string' ? detail : 'Réservation impossible pour le moment. Réessaie.');
      setEtat(avant);
    }
  };

  return (
    <div data-testid={`evt-offert-${evt.offer_id}`} style={{ marginTop: '14px', padding: '14px', borderRadius: '14px',
      background: rgbaP(0.1), border: `1px solid ${rgbaP(0.35)}`, textAlign: 'left' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, color: 'rgba(255,255,255,0.96)', fontSize: '15px' }}>
        <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="gift" size={18} /></span>
        {evt.titre}
      </div>
      <p style={{ margin: '6px 0 2px', fontSize: '13.5px', color: 'rgba(255,255,255,0.8)' }}>
        {quandEvenement(evt.datetime)}{evt.lieu ? ` · ${evt.lieu}` : ''}
      </p>
      <p data-testid="evt-offert-tarif" style={{ margin: '0 0 12px', fontSize: '14px', fontWeight: 700, color: PRIMAIRE }}>
        Ton tarif membre : OFFERT
      </p>
      {etat === 'reservee' ? (
        <>
          <p data-testid="evt-offert-reservee" style={{ margin: '0 0 8px', fontSize: '14px', color: 'rgba(255,255,255,0.92)', fontWeight: 600 }}>
            Ta place est réservée.
          </p>
          {relais ? (
            <InviterMesAmis relaisInitial={relais} />
          ) : (
            <button type="button" data-testid="evt-offert-lien" onClick={reserver}
                    style={{ width: '100%', minHeight: '44px', borderRadius: '12px', background: 'rgba(255,255,255,0.06)',
                      border: '1px solid rgba(255,255,255,0.14)', color: 'rgba(255,255,255,0.92)', fontWeight: 600, fontSize: '14px', cursor: 'pointer' }}>
              Inviter mes amis
            </button>
          )}
        </>
      ) : (
        <button type="button" data-testid="evt-offert-reserver" onClick={reserver} disabled={etat === 'envoi'}
                style={{ width: '100%', minHeight: '46px', borderRadius: '12px', border: 'none', background: PRIMAIRE,
                  color: 'rgba(255,255,255,1)', fontWeight: 700, fontSize: '15px', cursor: 'pointer', opacity: etat === 'envoi' ? 0.7 : 1 }}>
          {etat === 'envoi' ? 'Réservation…' : 'Réserver ma place offerte'}
        </button>
      )}
      {erreur ? <p data-testid="evt-offert-erreur" style={{ margin: '8px 0 0', fontSize: '13px', color: 'rgba(255,170,170,1)' }}>{erreur}</p> : null}
    </div>
  );
}

export default function EvenementsOfferts({ evenements, accessCode, memberSlug }) {
  const liste = Array.isArray(evenements) ? evenements.filter((e) => e && e.offer_id) : [];
  if (!liste.length || !accessCode) return null;
  return (
    <div data-testid="evenements-offerts">
      {liste.map((e) => <CarteEvenement key={e.offer_id} evt={e} accessCode={accessCode} memberSlug={memberSlug} />)}
    </div>
  );
}

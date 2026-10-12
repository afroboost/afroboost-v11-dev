/**
 * V610 — « TA PLACE OFFERTE » DANS L'ESPACE (membres avec abonnement 8 mois actif).
 *
 * La liste vient du SERVEUR (`evenements_offerts` de GET /subscriber/space) : il a
 * déjà vérifié l'abonnement de CETTE personne (e-mail de la session d'espace) à la
 * date de l'événement. Ici, aucun calcul de droit — un clic, une réservation à
 * 0 CHF (POST …/evenement/<offre>/offert, idempotent), puis le lien personnel pour
 * inviter (facultatif). Aucun paiement, aucun Stripe.
 */
import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import SvgIcon from './SvgIcon';
import InviterMesAmis from './InviterMesAmis';
import { invitationActuelle } from '../utils/attribution';
import { lireIntentionMembre, oublierIntentionMembre, memoriserParticipation } from '../utils/participationEvenement'; // V610m

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

function CarteEvenement({ evt, accessCode, memberSlug, vise = false, jetonVise = '' }) {
  const [etat, setEtat] = useState(evt.deja_reserve ? 'reservee' : 'libre');
  const [relais, setRelais] = useState(null);
  const [erreur, setErreur] = useState('');
  const [vientDeReserver, setVientDeReserver] = useState(false);
  const carteRef = useRef(null);
  // V610m : venu de « Réserve gratuitement » sur l'invitation -> CETTE carte, à l'écran.
  useEffect(() => {
    if (!vise || !carteRef.current) return;
    try { carteRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (e) { /* ignore */ }
  }, [vise]);

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
      const rel = (r && r.data && r.data.relais) || null;
      setRelais(rel);
      setEtat('reservee');
      setVientDeReserver(avant === 'libre');
      // V610m : la place est prise -> l'intention est servie ; rouvrir l'invitation sur cet
      // appareil montrera « Tu participes » + le lien (jamais un paiement).
      if (vise) oublierIntentionMembre();
      const t = (inv && inv.t) || jetonVise;
      if (rel && t) memoriserParticipation(t, { relais: rel });
    } catch (e) {
      const detail = e && e.response && e.response.data && e.response.data.detail;
      setErreur(typeof detail === 'string' ? detail : 'Réservation impossible pour le moment. Réessaie.');
      setEtat(avant);
    }
  };

  return (
    <div ref={carteRef} data-testid={`evt-offert-${evt.offer_id}`} data-vise={vise ? '1' : '0'} style={{ marginTop: '14px', padding: vise ? '16px 14px' : '14px', borderRadius: '16px',
      background: rgbaP(vise ? 0.16 : 0.1), border: `${vise ? 2 : 1}px solid ${vise ? PRIMAIRE : rgbaP(0.35)}`, textAlign: 'left', scrollMarginTop: '12px' }}>
      {etat === 'reservee' && (vientDeReserver || vise) ? (
        <div data-testid="evt-offert-confirme" style={{ textAlign: 'center', marginBottom: '10px' }}>
          <span style={{ display: 'inline-flex', width: 48, height: 48, borderRadius: 999, alignItems: 'center', justifyContent: 'center', background: rgbaP(0.22), color: PRIMAIRE, marginBottom: 6 }}>
            <SvgIcon name="check" size={24} />
          </span>
          <div style={{ fontSize: '22px', fontWeight: 800, color: 'rgba(255,255,255,0.97)' }}>Ta place est réservée !</div>
        </div>
      ) : null}
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
            <InviterMesAmis relaisInitial={relais} autoLecture={vientDeReserver} />
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
  // V610m : l'événement VISÉ depuis l'invitation passe en tête, mis en évidence.
  const [intention] = useState(() => lireIntentionMembre());
  if (!accessCode) return null;
  const vise = intention ? liste.find((e) => String(e.offer_id) === intention.offre) : null;
  if (!liste.length && !intention) return null;
  const ordre = vise ? [vise].concat(liste.filter((e) => e !== vise)) : liste;
  return (
    <div data-testid="evenements-offerts">
      {intention && !vise ? (
        // Le serveur n'offre pas cet événement à CE compte : rien n'est inventé, on le dit.
        <p data-testid="evt-offert-non-eligible" role="status" style={{ margin: '14px 0 0', padding: '12px 14px', borderRadius: '14px',
          background: 'rgba(255,255,255,0.06)', fontSize: '14px', color: 'rgba(255,255,255,0.88)' }}>
          Cet événement n’est pas offert avec l’abonnement de ce compte. Tu peux réserver ta place depuis l’invitation
          {intention.jeton ? <> : <a href={`/i/${encodeURIComponent(intention.jeton)}`} onClick={() => oublierIntentionMembre()} style={{ color: PRIMAIRE, fontWeight: 700 }}>revenir à l’invitation</a></> : '.'}
        </p>
      ) : null}
      {ordre.map((e) => <CarteEvenement key={e.offer_id} evt={e} accessCode={accessCode} memberSlug={memberSlug}
                                        vise={e === vise} jetonVise={intention ? intention.jeton : ''} />)}
    </div>
  );
}

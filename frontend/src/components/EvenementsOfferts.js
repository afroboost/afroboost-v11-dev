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
import { villeDuLieu } from '../utils/invitationCampagne'; // V618L
import { chf } from '../utils/avantagesMembres'; // V618M
import ConditionsParticipation from './ConditionsParticipation'; // V618M : conditions AU MOMENT de réserver

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

/** V618L — « Mercredi 28 octobre · 18h45 » (majuscule : c'est une ligne à part entière). */
export function quandEvenementLigne(iso) {
  const q = quandEvenement(iso);
  return q ? q.charAt(0).toUpperCase() + q.slice(1) : '';
}

/** V618L — « Voir ma réservation » : l'espace rechargé, ouvert sur « Mes prochaines séances ». */
export function voirMaReservation() {
  try {
    window.history.scrollRestoration = 'manual';   // pas de retour à l'ancienne position
    window.location.hash = 'mes-seances';
    window.location.reload();
  } catch (e) { /* ignore */ }
}

const EVT_RESERVE = 'af-evt-reserve';   // V618M : la carte du haut et celle de l'agenda restent d'accord

/** V618M — la carte de l'AGENDA depuis une date « événement » : l'avantage personnel (serveur)
 *  si la personne en a un, sinon le tarif public du moment (serveur). */
export function evtDeLOccurrence(occ, data, confirme = false) {
  const o = occ || {};
  const offert = ((data && data.evenements_offerts) || []).find((e) => e && e.offer_id === o.offer_id);
  if (offert) return confirme && !offert.deja_reserve ? Object.assign({}, offert, { deja_reserve: true }) : offert;
  const m = /^\/i\/([A-Za-z0-9_-]{8,80})$/.exec(String(o.lien_evenement || ''));
  const pub = Number(o.prix_public);
  return { offer_id: o.offer_id, titre: o.name || o.course_name || 'Événement', datetime: o.datetime, lieu: o.locationName || o.location || '',
    deja_reserve: !!confirme, complet: !!o.complet, jeton_invitation: m ? m[1] : '',
    avantage: Number.isFinite(pub) ? { type: 'aucun', valeur: null, prix_public: pub, prix_membre: pub } : null };
}

export function CarteEvenement({ evt, accessCode, memberSlug, vise = false, jetonVise = '', jetonEspace = '', courseId = '',
  conditionsAcceptees, onConditions, sansEntete = false }) {
  const [etat, setEtat] = useState(evt.deja_reserve ? 'reservee' : 'libre');
  const [etape, setEtape] = useState('');                 // '' | 'conditions'
  const [condLocal, setCondLocal] = useState(false);
  const [condRequises, setCondRequises] = useState(null);  // null = pas encore su
  const [details, setDetails] = useState(null);            // null = fermé ; objet = page publique lue
  const accepte = typeof conditionsAcceptees === 'boolean' ? conditionsAcceptees : condLocal;
  const setAccepte = (v) => { if (typeof onConditions === 'function') onConditions(v); else setCondLocal(v); };
  // V618M : réservée ailleurs (l'autre carte du même événement) -> cette carte le sait aussi.
  useEffect(() => {
    const surReserve = (e) => { if (e && e.detail && e.detail.offre === evt.offer_id) setEtat((x) => (x === 'reservee' ? x : 'reservee')); };
    window.addEventListener(EVT_RESERVE, surReserve);
    return () => window.removeEventListener(EVT_RESERVE, surReserve);
  }, [evt.offer_id]);
  const [relais, setRelais] = useState(null);
  const [erreur, setErreur] = useState('');
  const [vientDeReserver, setVientDeReserver] = useState(false);
  const carteRef = useRef(null);
  // V610m : venu de « Réserve gratuitement » sur l'invitation -> CETTE carte, à l'écran.
  // V618L (Playwright, mobile 390) : un défilement animé unique finissait AU-DELÀ de la carte
  // (la page se met encore en page au-dessus pendant l'animation). On place la carte sans
  // animation, puis on corrige deux fois si elle a glissé — jamais en boucle.
  useEffect(() => {
    if (!vise) return undefined;
    const placer = () => {
      const el = carteRef.current;
      if (!el) return;
      const h = el.getBoundingClientRect().top;
      if (h < 0 || h > window.innerHeight * 0.5) { try { el.scrollIntoView({ behavior: 'auto', block: 'start' }); } catch (e) { /* ignore */ } }
    };
    const t = [setTimeout(placer, 50), setTimeout(placer, 600), setTimeout(placer, 1500)];
    return () => t.forEach(clearTimeout);
  }, [vise]);
  // V610p : événement visé DÉJÀ réservé -> son lien personnel tout de suite (la route est
  // idempotente : elle rend la réservation et le lien existants, rien n'est recréé).
  const dejaVu = useRef(false);
  useEffect(() => {
    // V618M : seule une place OFFERTE se relit par la route « offert » ; un billet payé au tarif
    // membre a son lien dans « Mes événements » (plus bas dans l'espace).
    // V618N : visée OU NON (agenda, retour plus tard) — le membre retrouve « Inviter mes amis ».
    if (!evt.deja_reserve || dejaVu.current || (evt.avantage && evt.avantage.type !== 'gratuit')) return;
    dejaVu.current = true;
    reserver();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [evt.deja_reserve]);

  // V618M — l'avantage RÉEL de cette personne (décidé par le serveur) : gratuit -> réservation
  // à 0 CHF ici ; réduction / prix fixe -> paiement Stripe au prix MEMBRE calculé par le serveur.
  const av = evt.avantage || { type: 'gratuit' };
  const gratuit = av.type === 'gratuit';
  const payer = async () => {
    if (etat === 'envoi') return;
    setEtat('envoi');
    setErreur('');
    try {
      const inv = invitationActuelle();
      const jeton = evt.jeton_invitation || jetonVise || (inv && inv.t) || '';
      const r = await fetch(`${BACKEND_URL}/api/create-checkout-session`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'x-espace-token': jetonEspace || '' },
        body: JSON.stringify({ productName: String(evt.titre || '').slice(0, 120), amount: Number(av.prix_membre) || 0, offerId: evt.offer_id,
          quantity: 1, originUrl: window.location.origin, attribution: jeton ? { invitation: jeton } : undefined, retourInvitation: true,
          espace: { code: accessCode, slug: memberSlug || '' } }),
      });
      const j = await r.json().catch(() => ({}));
      if (r.ok && j && typeof j.url === 'string' && /^https?:\/\//.test(j.url)) { window.location.href = j.url; return; }
      setErreur((j && typeof j.detail === 'string') ? j.detail : 'Le paiement ne peut pas s’ouvrir pour le moment. Réessaie.');
      setEtat('libre');
    } catch (e) {
      setErreur('Connexion impossible. Vérifie ton réseau et réessaie.');
      setEtat('libre');
    }
  };

  const agir = () => (gratuit ? reserver() : payer());
  // V618M — les CONDITIONS se demandent au moment de réserver (jamais avant, jamais perdues) :
  // déjà acceptées -> on réserve ; sinon l'étape s'ouvre ici, dans la carte.
  const surCta = () => {
    if (etat === 'envoi') return;
    if (accepte || condRequises === false) { setEtape(''); agir(); return; }
    setEtape('conditions');
  };
  const ouvrirDetails = () => {
    if (details) { setDetails(null); return; }
    const j = evt.jeton_invitation || jetonVise;
    setDetails({ chargement: true });
    if (!j || typeof fetch !== 'function') { setDetails({}); return; }
    fetch(`${BACKEND_URL}/api/invitation/publique/${encodeURIComponent(j)}`)
      .then((x) => (x.ok ? x.json() : {})).then((d) => setDetails(d || {})).catch(() => setDetails({}));
  };

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
      try { window.dispatchEvent(new CustomEvent(EVT_RESERVE, { detail: { offre: evt.offer_id } })); } catch (x) { /* ignore */ }
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
    <div ref={carteRef} id={`evt-offert-${evt.offer_id}`} data-testid={`evt-offert-${evt.offer_id}`} data-vise={vise ? '1' : '0'} style={{ marginTop: '14px', padding: vise ? '16px 14px' : '14px', borderRadius: '16px',
      background: rgbaP(vise ? 0.16 : 0.1), border: `${vise ? 2 : 1}px solid ${vise ? PRIMAIRE : rgbaP(0.35)}`, textAlign: 'left', scrollMarginTop: '12px' }}>
      {/* V618N : toute place prise s'annonce en TITRE (réservée à l'instant, ou déjà réservée). */}
      {etat === 'reservee' ? (
        <div data-testid="evt-offert-confirme" style={{ textAlign: 'center', marginBottom: '10px' }}>
          <span style={{ display: 'inline-flex', width: 48, height: 48, borderRadius: 999, alignItems: 'center', justifyContent: 'center', background: rgbaP(0.22), color: PRIMAIRE, marginBottom: 6 }}>
            <SvgIcon name="check" size={24} />
          </span>
          <div data-testid="evt-offert-confirme-titre" style={{ fontSize: '22px', fontWeight: 800, color: 'rgba(255,255,255,0.97)' }}>
            {vientDeReserver ? 'Ta place est réservée !' : 'Ta place est déjà réservée'}
          </div>
        </div>
      ) : null}
      {/* V618M : dans l'agenda, la date choisie affiche DÉJÀ titre, date et lieu — jamais deux fois. */}
      {sansEntete && etat !== 'reservee' ? null : (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, color: 'rgba(255,255,255,0.96)', fontSize: '15px' }}>
            <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="gift" size={18} /></span>
            {evt.titre}
          </div>
          {/* V618L : deux lignes courtes — la date, puis la ville (l'adresse complète est sur la page). */}
          <p data-testid="evt-offert-quand" style={{ margin: '6px 0 0', fontSize: '14px', color: 'rgba(255,255,255,0.88)' }}>{quandEvenementLigne(evt.datetime)}</p>
          {evt.lieu ? <p data-testid="evt-offert-ville" style={{ margin: '2px 0 0', fontSize: '14px', color: 'rgba(255,255,255,0.75)' }}>{villeDuLieu(evt.lieu) || evt.lieu}</p> : null}
        </>
      )}
      {etat !== 'reservee' ? (
        // V618M : l'avantage réel — « PLACE OFFERTE », ou « 24 CHF au lieu de 30 CHF », ou « 20 CHF ».
        <div data-testid="evt-offert-tarif" style={{ margin: '10px 0 12px' }}>
          <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.75)', display: 'flex', alignItems: 'center', gap: 6 }}>
            {av.type !== 'aucun' ? <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="heart" size={14} /></span> : null}
            {av.type === 'aucun' ? 'Tarif actuel' : (av.type === 'prix_fixe' ? 'Ton tarif membre' : 'Ton avantage membre')}
          </div>
          <div data-testid="evt-offert-avantage" style={{ fontSize: 18, fontWeight: 800, color: av.type === 'aucun' ? 'rgba(255,255,255,0.95)' : PRIMAIRE }}>
            {gratuit ? 'PLACE OFFERTE' : (av.type === 'reduction' ? `-${av.valeur} %` : chf(av.prix_membre))}
          </div>
          {av.type === 'reduction' && Number(av.prix_public) > Number(av.prix_membre) ? (
            <div data-testid="evt-offert-calcul" style={{ fontSize: 14, color: 'rgba(255,255,255,0.85)' }}>{chf(av.prix_public)} → {chf(av.prix_membre)}</div>
          ) : null}
        </div>
      ) : <div style={{ height: 6 }} />}
      {etat === 'reservee' ? (
        <>
          {/* V618L : jamais « Ta place est réservée » deux fois — le titre du haut suffit ; une
              place prise HORS de ce parcours (carte non visée) le dit en une ligne. */}
          {relais ? (
            <InviterMesAmis relaisInitial={relais} autoLecture={vientDeReserver} voirReservation={voirMaReservation}
                            impactEspace={jetonEspace ? { code: accessCode, token: jetonEspace, slug: memberSlug || '' } : null} />
          ) : !gratuit ? (
            <p data-testid="evt-offert-lien-plus-bas" style={{ margin: 0, fontSize: 13, color: 'rgba(255,255,255,0.7)' }}>
              Ton lien pour inviter tes amis est dans « Mes événements ».
            </p>
          ) : (
            <button type="button" data-testid="evt-offert-lien" onClick={reserver}
                    style={{ width: '100%', minHeight: '44px', borderRadius: '12px', background: 'rgba(255,255,255,0.06)',
                      border: '1px solid rgba(255,255,255,0.14)', color: 'rgba(255,255,255,0.92)', fontWeight: 600, fontSize: '14px', cursor: 'pointer' }}>
              Inviter mes amis
            </button>
          )}
        </>
      ) : (
        evt.complet ? (
          <p data-testid="evt-offert-complet" role="status" style={{ margin: 0, fontWeight: 700 }}>Cet événement est complet.</p>
        ) : (
        <>
        {etape === 'conditions' ? (
          <div data-testid="evt-offert-conditions" style={{ margin: '0 0 10px' }}>
            <ConditionsParticipation courseId={courseId || evt.course_id || ''} accepte={accepte} onChange={setAccepte}
                                     onRequired={(r) => { setCondRequises(r); if (!r) { setEtape(''); agir(); } }} />
          </div>
        ) : null}
        <button type="button" data-testid="evt-offert-reserver" onClick={surCta}
                disabled={etat === 'envoi' || (etape === 'conditions' && condRequises === true && !accepte)}
                style={{ width: '100%', minHeight: '46px', borderRadius: '12px', border: 'none', background: PRIMAIRE,
                  color: 'rgba(255,255,255,1)', fontWeight: 700, fontSize: '15px', cursor: 'pointer',
                  opacity: etat === 'envoi' || (etape === 'conditions' && condRequises === true && !accepte) ? 0.6 : 1 }}>
          {etat === 'envoi' ? (gratuit ? 'Réservation…' : 'Ouverture du paiement…')
            : (gratuit ? 'Réserver ma place offerte' : `Réserver à ${chf(av.prix_membre)}`)}
        </button>
        {/* V618M : « Voir les détails » s'ouvre ICI — on ne quitte jamais l'espace (date, état et
            conditions restent tels quels). */}
        <button type="button" data-testid="evt-offert-details" onClick={ouvrirDetails} aria-expanded={!!details}
                style={{ width: '100%', minHeight: 44, marginTop: 6, background: 'none', border: 'none', color: 'rgba(255,255,255,0.8)',
                  fontSize: 13.5, textDecoration: 'underline', cursor: 'pointer' }}>
          {details ? 'Masquer les détails' : 'Voir les détails'}
        </button>
        {details ? (
          <div data-testid="evt-offert-details-contenu" style={{ marginTop: 4, padding: 12, borderRadius: 12, background: 'rgba(255,255,255,0.05)', fontSize: 13.5, color: 'rgba(255,255,255,0.88)' }}>
            {details.chargement ? 'Chargement…' : (
              <>
                {evt.lieu ? <p style={{ margin: '0 0 8px', display: 'flex', gap: 6 }}><SvgIcon name="mapPin" size={15} /> {evt.lieu}</p> : null}
                {details.description ? <p style={{ margin: 0, whiteSpace: 'pre-line' }}>{details.description}</p> : null}
                {!details.description && !evt.lieu ? <p style={{ margin: 0 }}>Aucun détail supplémentaire.</p> : null}
              </>
            )}
          </div>
        ) : null}
        </>
        )
      )}
      {erreur ? <p data-testid="evt-offert-erreur" style={{ margin: '8px 0 0', fontSize: '13px', color: 'rgba(255,170,170,1)' }}>{erreur}</p> : null}
    </div>
  );
}

export default function EvenementsOfferts({ evenements, accessCode, memberSlug, jetonEspace }) {
  const liste = Array.isArray(evenements) ? evenements.filter((e) => e && e.offer_id) : [];
  // V610m : l'événement VISÉ depuis l'invitation passe en tête, mis en évidence.
  const [intention] = useState(() => lireIntentionMembre());
  const vise = intention ? liste.find((e) => String(e.offer_id) === intention.offre) : null;
  // V618M : sans avantage pour cet événement, on dit le TARIF ACTUEL (lu sur la page publique).
  const [prixPublic, setPrixPublic] = useState(null);
  const jetonNonEligible = intention && !vise && accessCode ? String(intention.jeton || '') : '';
  useEffect(() => {
    if (!jetonNonEligible || typeof fetch !== 'function') return undefined;
    let vivant = true;
    fetch(`${BACKEND_URL}/api/invitation/publique/${encodeURIComponent(jetonNonEligible)}`)
      .then((x) => (x.ok ? x.json() : null))
      .then((d) => { const p = d && d.prix_actif && Number(d.prix_actif.prix); if (vivant && Number.isFinite(p)) setPrixPublic(p); })
      .catch(() => {});
    return () => { vivant = false; };
  }, [jetonNonEligible]);
  if (!accessCode) return null;
  if (!liste.length && !intention) return null;
  const ordre = vise ? [vise].concat(liste.filter((e) => e !== vise)) : liste;
  return (
    <div data-testid="evenements-offerts">
      {intention && !vise ? (
        // Le serveur n'offre pas cet événement à CE compte : rien n'est inventé, on le dit.
        // V610o : on RESTE sur cet événement — la phrase, puis la réservation au tarif du moment.
        <div data-testid="evt-offert-non-eligible" role="status" style={{ margin: '14px 0 0', padding: '14px', borderRadius: '16px',
          background: 'rgba(255,255,255,0.06)', border: `1px solid ${rgbaP(0.3)}`, fontSize: '14.5px', color: 'rgba(255,255,255,0.92)' }}>
          {/* V618M : aucun avantage pour CET abonnement (réglage du coach) — le tarif public, dit tel quel. */}
          <p style={{ margin: '0 0 6px' }}>Ton abonnement ne comprend pas d’avantage pour cet événement.</p>
          {prixPublic != null ? <p data-testid="evt-offert-tarif-public" style={{ margin: '0 0 10px', fontWeight: 700 }}>Tarif actuel : {chf(prixPublic)}</p> : null}
          {intention.jeton ? (
            <a href={`/i/${encodeURIComponent(intention.jeton)}`} data-testid="evt-offert-tarif-actuel" onClick={() => oublierIntentionMembre()}
               style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 48, borderRadius: 12, background: PRIMAIRE,
                 color: 'rgba(255,255,255,1)', fontWeight: 800, textDecoration: 'none' }}>
              Réserver au tarif actuel
            </a>
          ) : null}
        </div>
      ) : null}
      {ordre.map((e) => <CarteEvenement key={e.offer_id} evt={e} accessCode={accessCode} memberSlug={memberSlug}
                                        vise={e === vise} jetonVise={intention ? intention.jeton : ''} jetonEspace={jetonEspace || ''} />)}
    </div>
  );
}

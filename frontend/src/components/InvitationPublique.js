/**
 * V607 — LA PAGE PUBLIQUE D'UNE INVITATION : afroboost.com/i/<jeton>.
 *
 * Le lien COURT des invitations (coach ou participant d'un événement). Le serveur
 * a déjà posé, dans le HTML, les balises Open Graph PROPRES à l'invitation (ce que
 * WhatsApp affiche) ; cette page montre la même chose, en mieux, puis envoie vers le
 * parcours EXISTANT du type (`cible` du serveur) :
 *   - Essai gratuit  -> la chaîne de l'essai (`/duo/c/<jeton>`) ;
 *   - Pass Duo       -> le Centre Parrainage ;
 *   - Événement      -> la vitrine (`/?offre=<id>&inv=<jeton>`), réservation / paiement.
 * Rien n'est réservé ni payé ici.
 *
 * MÉDIAS : vidéo SANS lecture automatique (poster, lecture au clic, contrôles du
 * navigateur : lecture, pause, son), `preload="none"` ; « un mot audio » lu
 * SEULEMENT au clic. La page est complète sans eux.
 * SUIVI honnête : `lien_ouvert` à l'affichage, `reservation_commencee` au clic.
 * COULEURS : var(--primary-color) / rgba(var(--primary-rgb)) ; icônes SVG.
 */
import React, { useEffect, useRef, useState } from 'react';
import SvgIcon from './SvgIcon';
import { suivreInvitation } from '../utils/invitationSuivi';
import { DemandeLienMembre } from './AccesMembreEvenement'; // V610b / V618L : une seule étape
import AfroboostAudioPlayer from './AfroboostAudioPlayer'; // V610g
import InviterMesAmis from './InviterMesAmis'; // V610i : après réservation confirmée
import { attributionActuelle, invitationEnregistrer } from '../utils/attribution';
import { lireSession, urlDeLaSession } from '../utils/espaceSession';
import { memoriserParticipation, lireParticipation, retenirIntentionMembre, offreDeLInvitation } from '../utils/participationEvenement'; // V610m
import { titreLisible, villeDuLieu } from '../utils/invitationCampagne'; // V610o / V618L

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;
// V610j — UNE colonne pour tout (vidéo, contenu, bouton) : compacte et centrée sur ordinateur,
// presque pleine largeur sur téléphone ; le bouton s'aligne sur le contenu (marges de 16 px).
const COLONNE = '440px';
const COLONNE_INTERIEURE = '408px';   // COLONNE − 2 × 16 px de marge

function maj(t) {
  const s = String(t || '').trim();
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
}

/** https ou chemin du même site, jamais `//hôte` ni un autre schéma. */
export function urlSure(u) {
  const s = typeof u === 'string' ? u.trim() : '';
  if (!s || /[\s"'<>\\]/.test(s)) return '';
  if (/^\/(?!\/)/.test(s)) return `${BACKEND_URL}${s}`;
  return /^https:\/\//i.test(s) ? s : '';
}

/** La cible du bouton : TOUJOURS un chemin de CE site (le serveur rend l'adresse
 *  complète du front ; on n'en garde que le chemin) — jamais un autre site. */
export function cibleSure(c) {
  const s = typeof c === 'string' ? c.trim() : '';
  if (!s) return '/';
  try {
    const u = new URL(s, window.location.origin);
    const chemin = u.pathname + u.search;
    return /^\/(?!\/)/.test(chemin) ? chemin : '/';
  } catch (e) { return '/'; }
}

/** « 25 CHF » / « 12.50 CHF ». */
function prixTexte(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return '';
  return `${Number.isInteger(v) ? v : v.toFixed(2)} CHF`;
}

/** V618L — « mercredi 21 octobre à 18h45 » : le jour ET l'heure exacte de la bascule (heure
 *  de Zurich, donnée par le serveur). Sans l'heure, « dès le 21 » laissait croire à minuit. */
export function jourBascule(iso) {
  try {
    const p = new Intl.DateTimeFormat('fr-CH', { weekday: 'long', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Zurich' })
      .formatToParts(new Date(iso)).reduce((a, x) => Object.assign(a, { [x.type]: x.value }), {});
    if (!p.day) return '';
    return `${p.weekday} ${p.day} ${p.month} à ${p.hour}h${p.minute}`;
  } catch (e) { return ''; }
}

/** V618L — « Je réserve ma place — 25 CHF » : le prix ACTUEL (serveur) dans le bouton. */
export function libelleCta(d, pa) {
  const base = String((d && d.cta_label) || '').trim() || 'Je réserve ma place';
  const prix = pa && Number.isFinite(Number(pa.prix)) && Number(pa.prix) > 0 ? prixTexte(pa.prix) : '';
  return prix && base.indexOf('CHF') < 0 ? `${base} — ${prix}` : base;
}

/** V618L — la promesse en une phrase, quand l'invitation n'a pas d'accroche à elle. */
export const PROMESSE_EVENEMENT = '1 heure de cardio-danse afro au casque, accessible à tous.';

/** « 21 octobre à 18h45 » — les conditions de prix, dans « Lire plus ». */
function finPalier(iso) {
  try {
    const p = new Intl.DateTimeFormat('fr-CH', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Zurich' })
      .formatToParts(new Date(iso)).reduce((a, x) => Object.assign(a, { [x.type]: x.value }), {});
    return `${p.day} ${p.month} à ${p.hour}h${p.minute}`;
  } catch (e) { return ''; }
}

function Ligne({ icone, children, testid }) {
  return (
    <div data-testid={testid} style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '15px', color: 'rgba(255,255,255,0.92)' }}>
      <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name={icone} size={18} /></span>
      <span>{children}</span>
    </div>
  );
}

/** V610g — le « mot » avant réservation, dans le lecteur Afroboost (au clic, jamais d'autoplay). */
function MotAudio({ url, prenom, inerte }) {
  return <AfroboostAudioPlayer src={url} titre={prenom ? `Un mot de ${prenom}` : 'Un mot pour toi'} testidBouton="inv-pub-audio" inerte={inerte} />;
}

/** V610i — le ratio RÉEL du média, en libellé lisible (« 9:16 », « 16:9 », « 1:1 », sinon « l:h »). */
export function libelleRatio(l, h) {
  const w = Number(l); const t = Number(h);
  if (!(w > 0) || !(t > 0)) return '';
  const r = w / t;
  if (Math.abs(r - 9 / 16) < 0.02) return '9:16';
  if (Math.abs(r - 16 / 9) < 0.02) return '16:9';
  if (Math.abs(r - 1) < 0.02) return '1:1';
  if (Math.abs(r - 4 / 5) < 0.02) return '4:5';
  if (Math.abs(r - 4 / 3) < 0.02) return '4:3';
  return `${Math.round(w)}:${Math.round(t)}`;
}

/**
 * V610i — LE LECTEUR S'ADAPTE À LA VIDÉO (et non l'inverse). Le cadre prend le ratio
 * lu dans les métadonnées (`preload="metadata"` : quelques Ko, jamais la vidéo) ;
 * avant elles, celui de l'affiche (même image que la miniature). L'affiche et la vidéo
 * occupent EXACTEMENT le même cadre : aucun saut au moment de « Lecture ».
 * Largeur = min(colonne, 78 % de la hauteur d'écran × ratio) : un 9:16 reste un « Reel »
 * centré sur ordinateur, prend presque toute la largeur sur téléphone ; un 16:9 occupe la
 * largeur. Jamais de recadrage forcé (contain sur un cadre du MÊME ratio = aucune bande).
 * Pas d'autoplay ; aucun « Télécharger » proposé (frein d'interface, pas un DRM).
 */
export function VideoAdaptative({ src, poster, titre, auto = false }) {
  const [dim, setDim] = useState(null);          // {l, h} de la VIDÉO
  const videoRef = useRef(null);
  // V610j — LECTURE AUTOMATIQUE EN BOUCLE (page publique) : muette au départ (seul autoplay
  // que les navigateurs autorisent), `playsInline` (iOS), `loop` ; le son s'active par les
  // contrôles. React ne pose pas toujours l'attribut `muted` : il est forcé ici, puis play().
  useEffect(() => {
    const v = videoRef.current;
    if (!auto || !v) return;
    v.muted = true;
    v.defaultMuted = true;
    const p = v.play();
    if (p && typeof p.catch === 'function') p.catch(() => { /* bloqué : l'affiche reste, Lecture au clic */ });
  }, [auto, src]);
  const [dimAffiche, setDimAffiche] = useState(null);
  useEffect(() => {
    if (!poster || dim) return undefined;
    let vivant = true;
    const img = new Image();
    img.onload = () => { if (vivant && img.naturalWidth && img.naturalHeight) setDimAffiche({ l: img.naturalWidth, h: img.naturalHeight }); };
    img.src = poster;
    return () => { vivant = false; };
  }, [poster, dim]);
  const d = dim || dimAffiche || { l: 9, h: 16 };
  const ratio = d.l / d.h;
  return (
    <div data-testid="inv-pub-video-cadre" data-ratio={libelleRatio(d.l, d.h)} data-source-ratio={dim ? 'video' : (dimAffiche ? 'affiche' : 'defaut')}
         style={{ width: `min(100%, calc(78vh * ${ratio.toFixed(4)}))`, aspectRatio: `${d.l} / ${d.h}`, margin: '0 auto 14px',
           borderRadius: '16px', overflow: 'hidden', background: 'rgb(0,0,0)', border: `1px solid ${rgbaP(0.25)}` }}>
      <video ref={videoRef} data-testid="inv-pub-video" src={src} poster={poster || undefined} controls playsInline
             preload={auto ? 'auto' : 'metadata'} autoPlay={auto} muted={auto} loop={auto}
             aria-label={titre || 'Vidéo de l’invitation'}
             controlsList="nodownload noremoteplayback" disableRemotePlayback onContextMenu={(e) => e.preventDefault()}
             onLoadedMetadata={(e) => {
               const v = e.currentTarget;
               if (v.videoWidth && v.videoHeight) setDim({ l: v.videoWidth, h: v.videoHeight });
             }}
             // V610j : `cover` sur un cadre AU RATIO DE LA VIDÉO = la vidéo n'est pas recadrée, et
             // l'affiche remplit EXACTEMENT le même cadre (jamais étirée, jamais de bandes).
             style={{ display: 'block', width: '100%', height: '100%', objectFit: 'cover', background: 'rgb(0,0,0)' }} />
    </div>
  );
}

/** V610i — « Lire plus » : SEULEMENT le complément (rien de ce qui est déjà affiché au-dessus). */
function LirePlus({ ouvert, setOuvert, children }) {
  return (
    <div style={{ margin: '0 0 14px', borderTop: '1px solid rgba(255,255,255,0.1)', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
      <button type="button" data-testid="inv-pub-lire-plus" aria-expanded={ouvert} onClick={() => setOuvert((v) => !v)}
              style={{ width: '100%', minHeight: '46px', padding: '10px 2px', background: 'none', border: 'none', color: 'rgba(255,255,255,0.92)',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '15px', fontWeight: 700, cursor: 'pointer' }}>
        {ouvert ? 'Lire moins' : 'Lire plus'} <SvgIcon name={ouvert ? 'arrowUp' : 'arrowDown'} size={16} />
      </button>
      {ouvert ? <div data-testid="inv-pub-lire-plus-contenu" style={{ padding: '0 2px 14px', display: 'grid', gap: '14px' }}>{children}</div> : null}
    </div>
  );
}

function Rubrique({ titre, children, testid }) {
  return (
    <section data-testid={testid}>
      <h2 style={{ margin: '0 0 4px', fontSize: '13px', letterSpacing: '0.06em', textTransform: 'uppercase', color: 'rgba(255,255,255,0.6)' }}>{titre}</h2>
      <div style={{ fontSize: '14.5px', color: 'rgba(255,255,255,0.86)', lineHeight: 1.5 }}>{children}</div>
    </section>
  );
}

/** V610m — l'événement confirmé : titre, puis date / heure / lieu (icônes SVG), centré. */
function PlaceEvenement({ titre, d }) {
  const x = d || {};
  return (
    <div data-testid="inv-pub-confirmation-evenement" style={{ margin: '0 0 8px' }}>
      <p style={{ margin: '0 0 6px', fontWeight: 800, fontSize: '16px' }}>{titre}</p>
      {/* V618L : « Mercredi 28 octobre · 18h45 », puis la ville — deux lignes, rien de plus. */}
      <div data-testid="inv-pub-confirmation-quand" style={{ display: 'grid', gap: '4px', justifyContent: 'center', fontSize: '14.5px', color: 'rgba(255,255,255,0.85)' }}>
        {x.date_label || x.time_label ? (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><SvgIcon name="calendar" size={15} />
            {[x.date_label ? maj(x.date_label) : '', String(x.time_label || '').replace(/^(\d{1,2}):(\d{2})$/, '$1h$2')].filter(Boolean).join(' · ')}</span>
        ) : null}
        {x.lieu ? <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><SvgIcon name="mapPin" size={15} /> {villeDuLieu(x.lieu) || x.lieu}</span> : null}
      </div>
    </div>
  );
}

/** V618L — « Voir ma réservation » : l'espace de CET appareil (session ouverte), sur « Mes
 *  prochaines séances ». Sans session : pas de bouton (l'e-mail de confirmation fait foi). */
export function voirReservationEspace() {
  const cible = urlDeLaSession(lireSession());
  if (!cible) return undefined;
  return () => { window.location.href = `${cible.split('#')[0]}#mes-seances`; };
}

/** V610m — revenir à la page de l'invitation (ex. réserver pour quelqu'un d'autre). */
function LienInvitation({ onClick }) {
  return (
    <button type="button" data-testid="inv-pub-voir-invitation" onClick={onClick}
            style={{ marginTop: 14, background: 'none', border: 'none', color: 'rgba(255,255,255,0.7)', fontSize: '13.5px', textDecoration: 'underline', cursor: 'pointer', minHeight: 44 }}>
      Voir l’invitation
    </button>
  );
}

/** V610m — place OFFERTE déjà mémorisée sur cet appareil (membre) : son lien, sans paiement. */
export function DejaParticipant({ d, relais, onIgnorer }) {
  const titre = (d && (d.title || d.offre_nom)) || 'Ton événement Afroboost';
  return (
    <div data-testid="inv-pub-confirmation" data-etat="participe" style={{ textAlign: 'center' }}>
      <span style={{ display: 'inline-flex', width: 56, height: 56, borderRadius: 999, alignItems: 'center', justifyContent: 'center', background: rgbaP(0.2), color: PRIMAIRE, marginBottom: 10 }}>
        <SvgIcon name="check" size={28} />
      </span>
      <h1 data-testid="inv-pub-place-reservee" style={{ margin: '0 0 8px', fontSize: '26px' }}>Ta place est déjà réservée</h1>
      <PlaceEvenement titre={titre} d={d} />
      <InviterMesAmis relaisInitial={relais} voirReservation={voirReservationEspace()} />
      <LienInvitation onClick={onIgnorer} />
    </div>
  );
}

const ESSAIS_CONFIRMATION = 20;      // ~45 s au total, puis un message clair (jamais une boucle)
const PAUSE_CONFIRMATION = (i) => 1500 + Math.min(i, 6) * 250;
const PAUSE_VERIFICATION = () => 500;   // V610m : lien rouvert — la place est déjà là, ou non

/**
 * V610i — RETOUR DE STRIPE (`/i/<jeton>?paiement=ok&cs=<session>`). Le retour du navigateur
 * ne prouve RIEN : la page attend que le WEBHOOK ait créé la place (`place_confirmee`) et le
 * lien personnel, puis seulement annonce « Ta place est réservée » et lance la boule de neige.
 */
export function ConfirmationReservation({ cs, d, jeton, participe = false, onIgnorer, attente = PAUSE_CONFIRMATION, essais = ESSAIS_CONFIRMATION }) {
  const [etat, setEtat] = useState({ statut: 'attente', relais: null });
  // V610m : place CONFIRMÉE par le serveur -> mémorisée sur cet appareil (rouvrir le lien
  // montre « Tu participes », jamais un nouveau paiement). Rien d'autre n'est gardé.
  useEffect(() => {
    if (etat.statut === 'confirmee' && jeton && !participe) memoriserParticipation(jeton, { cs });
  }, [etat.statut, jeton, cs, participe]);
  // V610m : participation mémorisée mais NON confirmée par le serveur -> la page normale.
  useEffect(() => {
    if (participe && etat.statut === 'delai' && typeof onIgnorer === 'function') onIgnorer();
  }, [participe, etat.statut, onIgnorer]);
  useEffect(() => {
    let vivant = true;
    (async () => {
      let relais = null;
      for (let i = 0; i < essais && vivant; i += 1) {
        try {
          const r = await fetch(`${BACKEND_URL}/api/invitation/relais/session/${encodeURIComponent(cs)}`, { headers: { Accept: 'application/json' } });
          if (r.ok) {
            relais = await r.json();
            if (relais && relais.place_confirmee) { if (vivant) setEtat({ statut: 'confirmee', relais }); return; }
          }
        } catch (e) { /* réseau : on retente */ }
        await new Promise((ok) => setTimeout(ok, attente(i)));
      }
      if (vivant) setEtat({ statut: 'delai', relais });
    })();
    return () => { vivant = false; };
  }, [cs, attente, essais]);

  const quand = [d && d.date_label ? maj(d.date_label) : '', d && d.time_label ? d.time_label : ''].filter(Boolean).join(' · ');
  const titre = (d && (d.title || d.offre_nom)) || (etat.relais && etat.relais.titre) || 'Ton événement Afroboost';
  return (
    <div data-testid="inv-pub-confirmation" data-etat={etat.statut} style={{ textAlign: 'center' }}>
      {etat.statut === 'attente' ? (
        <div role="status" style={{ padding: '40px 8px' }}>
          <div style={{ width: 44, height: 44, margin: '0 auto 14px', borderRadius: 999, border: `3px solid ${rgbaP(0.25)}`, borderTopColor: PRIMAIRE, animation: 'invRot 0.9s linear infinite' }} />
          <style>{'@keyframes invRot{to{transform:rotate(360deg)}}'}</style>
          <p data-testid="inv-pub-confirmation-attente" style={{ margin: 0, fontSize: '17px', fontWeight: 700 }}>{participe ? 'Vérification de ta place…' : 'Confirmation de ton paiement…'}</p>
          <p style={{ margin: '6px 0 0', fontSize: '13.5px', color: 'rgba(255,255,255,0.65)' }}>Quelques secondes, le temps que le paiement soit validé.</p>
        </div>
      ) : etat.statut === 'confirmee' ? (
        <div>
          <span style={{ display: 'inline-flex', width: 56, height: 56, borderRadius: 999, alignItems: 'center', justifyContent: 'center', background: rgbaP(0.2), color: PRIMAIRE, marginBottom: 10 }}>
            <SvgIcon name="check" size={28} />
          </span>
          <h1 data-testid="inv-pub-place-reservee" style={{ margin: '0 0 8px', fontSize: '26px' }}>{participe ? 'Ta place est déjà réservée' : 'Ta place est réservée !'}</h1>
          <PlaceEvenement titre={titre} d={d} />
          {participe ? null : <p style={{ margin: '0 0 6px', color: 'rgba(255,255,255,0.65)', fontSize: '13.5px' }}>Ton e-mail de confirmation arrive.</p>}
          <InviterMesAmis relaisInitial={etat.relais} autoLecture={!participe} impactCs={cs} voirReservation={voirReservationEspace()} />
          {participe && typeof onIgnorer === 'function' ? <LienInvitation onClick={onIgnorer} /> : null}
        </div>
      ) : (
        <div data-testid="inv-pub-confirmation-delai" role="alert" style={{ padding: '30px 8px' }}>
          <p style={{ margin: '0 0 8px', fontSize: '17px', fontWeight: 700 }}>La confirmation prend plus de temps que prévu</p>
          <p style={{ margin: '0 0 14px', fontSize: '14px', color: 'rgba(255,255,255,0.8)' }}>
            Si ton paiement a été accepté, ta place est enregistrée et l'e-mail de confirmation va arriver. Rien n'est débité deux fois.
            Sans nouvelles d'ici 15 minutes, écris-nous.
          </p>
          <button type="button" onClick={() => window.location.reload()} data-testid="inv-pub-confirmation-reessayer"
                  style={{ minHeight: 44, padding: '0 20px', borderRadius: 999, border: `1px solid ${rgbaP(0.5)}`, background: 'none', color: 'rgba(255,255,255,0.95)', fontWeight: 700, cursor: 'pointer' }}>
            Vérifier à nouveau
          </button>
        </div>
      )}
    </div>
  );
}

/** Les paramètres de retour posés par le SERVEUR dans `success_url` / `cancel_url`. */
export function retourPaiement(recherche) {
  try {
    const q = new URLSearchParams(recherche || '');
    const cs = String(q.get('cs') || '');
    if (q.get('paiement') === 'ok' && /^cs_[A-Za-z0-9_]{6,200}$/.test(cs)) return { ok: true, cs };
    if (q.get('paiement') === 'annule') return { annule: true };
  } catch (e) { /* ignore */ }
  return null;
}

/**
 * `apercu` (V610e, éditeur coach) : les données sont FOURNIES (rien n'est lu, aucun
 * suivi n'est écrit) et le bouton ne mène nulle part — c'est exactement l'écran de
 * l'invité, sans effet de bord.
 */
export default function InvitationPublique({ token, apercu }) {
  const [etat, setEtat] = useState(() => (apercu ? { charge: false, d: apercu, erreur: false } : { charge: true, d: null, erreur: false }));
  const suiviRef = useRef(false);
  const enApercu = !!apercu;
  const d0 = apercu || etat.d;
  const [lirePlus, setLirePlus] = useState(false);
  const [envoi, setEnvoi] = useState({ cours: false, erreur: '' });
  const membreRef = useRef(null);
  const [membreOuvert, setMembreOuvert] = useState(false);   // V618L : l'étape e-mail, sous le bouton
  const retour = enApercu ? null : retourPaiement(typeof window !== 'undefined' ? window.location.search : '');
  // V610m : participation déjà connue SUR CET APPAREIL (jamais pendant un retour de paiement).
  const [participation] = useState(() => (enApercu || retour ? null : lireParticipation(token)));
  const [ignorerParticipation, setIgnorerParticipation] = useState(false);
  const ignorer = React.useCallback(() => setIgnorerParticipation(true), []);

  useEffect(() => {
    if (enApercu) return undefined;
    // V610i : le jeton du lien (racine ou lien personnel) est MÉMORISÉ dès l'ouverture — un
    // membre qui file vers son espace garde son inviteur direct (jamais la gratuité).
    try { invitationEnregistrer(`?inv=${encodeURIComponent(token || '')}`); } catch (e) { /* ignore */ }
    let vivant = true;
    fetch(`${BACKEND_URL}/api/invitation/publique/${encodeURIComponent(token)}`, { headers: { Accept: 'application/json' } })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => { if (vivant) setEtat({ charge: false, d, erreur: false }); })
      .catch(() => { if (vivant) setEtat({ charge: false, d: null, erreur: true }); });
    return () => { vivant = false; };
  }, [token, enApercu]);

  useEffect(() => {
    if (enApercu || !etat.d || suiviRef.current || (retour && retour.ok)) return;
    suiviRef.current = true;
    suivreInvitation(token, 'lien_ouvert');
  }, [etat.d, token, enApercu, retour]);

  const cadre = { minHeight: enApercu ? '100%' : '100vh', background: 'rgb(8,4,12)', color: 'rgba(255,255,255,0.96)', fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif' };
  // V610i : retour de Stripe — l'écran de confirmation, même si la page de l'invitation
  // n'est plus lisible entre-temps (masquée) : la PLACE, elle, est vérifiée côté serveur.
  if (retour && retour.ok && !etat.charge) {
    return (
      <div style={cadre} data-testid="inv-pub">
        <main style={{ maxWidth: COLONNE, margin: '0 auto', padding: '28px 16px 40px', boxSizing: 'border-box' }}>
          <ConfirmationReservation cs={retour.cs} d={etat.d} jeton={token} />
        </main>
      </div>
    );
  }
  // V610m — lien ROUVERT sur l'appareil qui a déjà sa place : « Tu participes » (vérifié par
  // le serveur pour un paiement), jamais un second paiement proposé d'emblée.
  if (participation && !ignorerParticipation && !etat.charge && etat.d && !enApercu) {
    return (
      <div style={cadre} data-testid="inv-pub">
        <main style={{ maxWidth: COLONNE, margin: '0 auto', padding: '28px 16px 40px', boxSizing: 'border-box' }}>
          {participation.cs
            ? <ConfirmationReservation cs={participation.cs} d={etat.d} jeton={token} participe onIgnorer={ignorer} essais={2} attente={PAUSE_VERIFICATION} />
            : <DejaParticipant d={etat.d} relais={participation.relais} onIgnorer={ignorer} />}
        </main>
      </div>
    );
  }
  if (!enApercu && etat.charge) return <div style={cadre} data-testid="inv-pub-chargement" />;
  if (!d0 || (!enApercu && etat.erreur)) {
    return (
      <div style={Object.assign({}, cadre, { display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px', boxSizing: 'border-box' })}>
        <div style={{ maxWidth: '420px', textAlign: 'center' }} data-testid="inv-pub-indisponible">
          <h1 style={{ fontSize: '22px', margin: '0 0 10px' }}>Cette invitation n'est plus disponible</h1>
          <p style={{ color: 'rgba(255,255,255,0.7)', margin: '0 0 18px' }}>Elle a peut-être été archivée. Tu peux découvrir Afroboost directement.</p>
          <a href="/" style={{ display: 'inline-block', padding: '12px 22px', borderRadius: '999px', background: PRIMAIRE, color: 'rgba(255,255,255,1)', textDecoration: 'none', fontWeight: 700 }}>Découvrir Afroboost</a>
        </div>
      </div>
    );
  }

  const d = d0;
  const inv = d.inviter_display || {};
  const prenom = String(inv.prenom || '').trim();
  const photo = urlSure(inv.photo_url);
  const video = urlSure(d.video_url);
  const audio = urlSure(d.audio_url);
  const image = urlSure(d.image_url) || urlSure(d.card_url);
  const pa = d.prix_actif || null;
  const type = d.type;
  const directe = !enApercu && d.reservation_directe && d.reservation_directe.offer_id ? d.reservation_directe : null;
  const titre = type === 'trial' ? (prenom ? `${prenom} t'invite à découvrir Afroboost` : 'Découvre Afroboost')
    : (String(d.title || d.offre_nom || '').trim() || 'Invitation Afroboost');
  // V610o : « Bassi t'invite à Afroboost Silent » — le nom court et lisible de l'événement.
  const titreCourt = (titreLisible(titre).split(/\s+—\s+/)[0] || titre);

  // V610i — « Je réserve ma place » : UN billet, UNE offre -> Stripe DIRECTEMENT. Le serveur
  // fixe le prix (palier actif), la quantité (1) et l'adresse de retour (cette page) ; le
  // montant envoyé ici n'est qu'indicatif. Le jeton voyage pour la boule de neige.
  const reserverDirect = async () => {
    if (envoi.cours) return;
    setEnvoi({ cours: true, erreur: '' });
    try {
      const attribution = Object.assign({}, attributionActuelle() || { first: null, last: null }, { invitation: token });
      const r = await fetch(`${BACKEND_URL}/api/create-checkout-session`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ productName: titre.slice(0, 120), amount: pa ? Number(pa.prix) || 0 : 0, offerId: directe.offer_id,
          quantity: 1, originUrl: window.location.origin, attribution, retourInvitation: true }),
      });
      const j = await r.json().catch(() => ({}));
      if (r.ok && j && typeof j.url === 'string' && /^https?:\/\//.test(j.url)) { window.location.href = j.url; return; }
      setEnvoi({ cours: false, erreur: (j && typeof j.detail === 'string') ? j.detail : 'Le paiement ne peut pas s’ouvrir pour le moment. Réessaie.' });
    } catch (e) {
      setEnvoi({ cours: false, erreur: 'Connexion impossible. Vérifie ton réseau et réessaie.' });
    }
  };
  const surCta = () => {
    if (enApercu) return;                       // aperçu : aucun départ, aucun suivi
    suivreInvitation(token, 'reservation_commencee');
    if (directe) { reserverDirect(); return; }
    window.location.href = cibleSure(d.cible);
  };
  // V610i : « Membre Afroboost 8 mois ? Réserve gratuitement » — session déjà ouverte -> l'espace ;
  // sinon le bloc complet (e-mail -> lien d'accès, réponse NEUTRE) dans « Lire plus ».
  const surMembre = () => {
    if (enApercu) return;
    // V610m : l'espace s'ouvrira DIRECTEMENT sur CET événement (même après le lien e-mail).
    retenirIntentionMembre(offreDeLInvitation(d), token);
    const cible = urlDeLaSession(lireSession());
    if (cible) { window.location.href = cible; return; }
    setMembreOuvert(true);
    setTimeout(() => { try { membreRef.current && membreRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e) { /* ignore */ } }, 60);
  };
  const paliers = pa && pa.paliers && pa.paliers.length > 1 ? pa.paliers : null;
  // V610i : les conditions de prix (fin de chaque palier) — une information NOUVELLE, pas une répétition.
  const lignePaiement = paliers
    ? paliers.map((p) => `${p.libelle} ${prixTexte(p.prix)}${p.jusqu_a ? ` jusqu'au ${finPalier(p.jusqu_a)}` : ''}`).join(' · ')
    : (pa ? prixTexte(pa.prix) : '');

  return (
    <div style={cadre} data-testid="inv-pub">
      <main style={{ maxWidth: COLONNE, margin: '0 auto', padding: type === 'event_paid' ? '16px 16px 40px' : '16px 16px 120px', boxSizing: 'border-box' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
          {photo ? <img src={photo} alt="" width="40" height="40" style={{ width: '40px', height: '40px', borderRadius: '999px', objectFit: 'cover', border: `2px solid ${PRIMAIRE}` }} />
            : <span style={{ width: '40px', height: '40px', borderRadius: '999px', background: rgbaP(0.25), display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: PRIMAIRE }}><SvgIcon name="user" size={18} /></span>}
          {/* V610o : le prénom de l'INVITEUR DIRECT (coach ou participant de la boule de neige). */}
          <div data-testid="inv-pub-inviteur" style={{ fontSize: '15px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            {type === 'event_paid' || type === 'event_free'
              ? <>{prenom ? `${prenom} t'invite à ${titreCourt}` : `Invitation à ${titreCourt}`}
                  <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="fire" size={16} /></span>
                  <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="headphones" size={16} /></span></>
              : (prenom ? `${prenom} t'invite` : "On t'invite")}
          </div>
        </div>

        {retour && retour.annule ? (
          <p data-testid="inv-pub-paiement-annule" role="status" style={{ margin: '0 0 12px', padding: '10px 12px', borderRadius: 12, background: 'rgba(255,255,255,0.06)', fontSize: '14px' }}>
            Paiement annulé : rien n'a été débité. Tu peux réserver quand tu veux.
          </p>
        ) : null}

        {video ? <VideoAdaptative src={video} poster={image} titre={titre} auto={!enApercu} /> : (image ? (
          <div style={{ borderRadius: '16px', overflow: 'hidden', marginBottom: '14px' }}>
            <img data-testid="inv-pub-image" src={image} alt={titre} loading="lazy" width="1200" height="630"
                 style={{ display: 'block', width: '100%', height: 'auto', aspectRatio: '1200 / 630', objectFit: 'cover' }} />
          </div>
        ) : null)}

        <h1 data-testid="inv-pub-titre" style={{ fontSize: '25px', lineHeight: 1.2, margin: '0 0 6px' }}>{titre}</h1>
        {d.subtitle || type === 'event_paid' || type === 'event_free' ? (
          <p data-testid="inv-pub-accroche" style={{ color: 'rgba(255,255,255,0.82)', margin: '0 0 12px', fontSize: '15px' }}>{d.subtitle || PROMESSE_EVENEMENT}</p>
        ) : null}
        {type === 'trial' ? (
          <p data-testid="inv-pub-pitch" style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'rgba(255,255,255,0.85)', margin: '0 0 12px', fontSize: '15px' }}>
            <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="headphones" size={18} /></span>
            Cardio + danse afro + casques immersifs, cours d'1 h.
          </p>
        ) : null}

        <div style={{ display: 'grid', gap: '6px', margin: '0 0 14px' }}>
          {d.date_label ? <Ligne icone="calendar" testid="inv-pub-date">{maj(d.date_label)}</Ligne> : null}
          {d.time_label ? <Ligne icone="clock" testid="inv-pub-heure">{d.time_label}</Ligne> : null}
          {d.lieu ? <Ligne icone="mapPin" testid="inv-pub-lieu">{d.lieu}</Ligne> : null}
        </div>

        {type === 'trial' ? (
          <div data-testid="inv-pub-offert" style={{ padding: '12px 14px', borderRadius: '14px', background: rgbaP(0.14), border: `1px solid ${rgbaP(0.4)}`, margin: '0 0 14px', display: 'flex', alignItems: 'center', gap: '10px', fontWeight: 700 }}>
            <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="gift" size={20} /></span> Ton premier cours est offert
          </div>
        ) : null}
        {type === 'event_free' ? (
          <div data-testid="inv-pub-gratuit" style={{ padding: '12px 14px', borderRadius: '14px', background: rgbaP(0.14), border: `1px solid ${rgbaP(0.4)}`, margin: '0 0 14px', fontWeight: 700 }}>
            Gratuit — inscription libre
          </div>
        ) : null}
        {type === 'event_paid' && pa ? (
          <div data-testid="inv-pub-prix" style={{ margin: '0 0 12px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', flexWrap: 'wrap' }}>
              <span data-testid="inv-pub-prix-actif" style={{ fontSize: '28px', fontWeight: 800 }}>{prixTexte(pa.prix)}</span>
              {pa.palier !== 'regular' ? <span style={{ fontSize: '14px', color: PRIMAIRE, fontWeight: 700 }}>{pa.libelle}</span> : null}
            </div>
            {/* V618L : UN prix — l'actuel. Les trois paliers et leurs dates sont dans « Lire plus » ;
                « 50 PLACES » n'apparaît que pour une capacité RÉELLE (le serveur décide). */}
            {d.message_places ? (
              <p data-testid="inv-pub-places" style={{ margin: '8px 0 0', fontSize: '14px', fontWeight: 800, display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="fire" size={16} /></span> {d.message_places}
              </p>
            ) : null}
            {/* V618M : compteur RÉEL, seulement si le coach a activé une capacité. */}
            {d.places_restantes != null && !d.complet ? (
              <p data-testid="inv-pub-places-restantes" style={{ margin: '6px 0 0', fontSize: '13.5px', fontWeight: 700 }}>
                {d.places_restantes} place{d.places_restantes > 1 ? 's' : ''} restante{d.places_restantes > 1 ? 's' : ''}
              </p>
            ) : null}
            {pa.prochain ? (
              <p data-testid="inv-pub-urgence" style={{ margin: '8px 0 0', fontSize: '13px', color: 'rgba(255,255,255,0.75)' }}>
                {prixTexte(pa.prochain.prix)} dès le {jourBascule(pa.prochain.a_partir_de)}.
              </p>
            ) : null}
          </div>
        ) : null}

        {type === 'event_paid' ? (
          // V618L : le bouton de réservation À SA PLACE (après le prix), avec le prix dedans.
          <div style={{ margin: '4px 0 14px' }}>
            {envoi.erreur ? (
              <p data-testid="inv-pub-cta-erreur" role="alert" style={{ margin: '0 0 8px', fontSize: '13.5px', color: 'rgba(255,190,180,1)', textAlign: 'center' }}>{envoi.erreur}</p>
            ) : null}
            {/* V618M : « Complet » SEULEMENT si le coach a activé une capacité réelle et qu'elle est atteinte. */}
            <button type="button" onClick={d.complet ? undefined : surCta} data-testid="inv-pub-cta" disabled={envoi.cours || !!d.complet}
                    style={{ display: 'block', width: '100%', minHeight: '54px', borderRadius: '999px', border: 'none',
                      background: d.complet ? 'rgba(255,255,255,0.12)' : PRIMAIRE, color: 'rgba(255,255,255,1)', fontSize: '17px', fontWeight: 800,
                      cursor: d.complet ? 'default' : 'pointer', opacity: envoi.cours ? 0.75 : 1 }}>
              {d.complet ? 'Complet' : (envoi.cours ? 'Ouverture du paiement…' : libelleCta(d, pa))}
            </button>
          </div>
        ) : null}

        {type === 'event_paid' && d.gratuit_membres ? (
          <div ref={membreRef} data-testid="inv-pub-gratuit-membres" style={{ margin: '0 0 10px' }}>
            <button type="button" data-testid="inv-pub-membre-compact" onClick={surMembre} aria-expanded={membreOuvert}
                    style={{ display: 'flex', alignItems: 'center', gap: '8px', width: '100%', padding: '12px 14px', borderRadius: 14, background: rgbaP(0.08),
                      border: `1px solid ${rgbaP(0.35)}`, color: 'rgba(255,255,255,0.92)', fontSize: '14.5px', cursor: 'pointer', textAlign: 'left', flexWrap: 'wrap' }}>
              <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="heart" size={16} /></span>
              {/* V618M : jamais « 8 mois » en dur — l'avantage dépend de l'abonnement de la personne. */}
              <span>Déjà membre Afroboost ?</span>
              <strong style={{ color: PRIMAIRE }}>Voir mon tarif membre</strong>
            </button>
            {membreOuvert ? (
              <div style={{ marginTop: 8 }}>
                <DemandeLienMembre inerte={enApercu} avantEnvoi={() => retenirIntentionMembre(offreDeLInvitation(d), token)}
                                   offreVisee={offreDeLInvitation(d)} jetonInvitation={enApercu ? '' : token} />
              </div>
            ) : null}
          </div>
        ) : null}

        {(d.description || (type === 'event_paid' && (pa || d.message || audio))) ? (
          <LirePlus ouvert={lirePlus} setOuvert={setLirePlus}>
            {d.description ? (
              <Rubrique titre="À propos" testid="inv-pub-a-propos">
                <p data-testid="inv-pub-description" style={{ margin: 0, whiteSpace: 'pre-line' }}>{d.description}</p>
              </Rubrique>
            ) : null}
            {type === 'event_paid' && pa ? (
              <Rubrique titre="Paiement" testid="inv-pub-paiement">
                Paiement sécurisé par carte ou TWINT. Le tarif est celui du moment de ta réservation
                {lignePaiement ? ` (${lignePaiement})` : ''}. Les ventes ferment au début de l'événement.
              </Rubrique>
            ) : null}
            {type === 'event_paid' && d.message ? (
              <Rubrique titre="Le mot du coach" testid="inv-pub-mot">
                <span data-testid="inv-pub-message" style={{ whiteSpace: 'pre-line' }}>{d.message}</span>
              </Rubrique>
            ) : null}
            {type === 'event_paid' && audio ? <div style={{ margin: '0 0 14px' }}><MotAudio url={audio} prenom={prenom} inerte={enApercu} /></div> : null}
          </LirePlus>
        ) : null}

        {d.message && type !== 'event_paid' ? (
          <p data-testid="inv-pub-message" style={{ margin: '0 0 14px', padding: '12px 14px', borderRadius: '14px', background: 'rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.88)', fontSize: '15px', whiteSpace: 'pre-line' }}>
            {d.message}
          </p>
        ) : null}
        {/* V610m : l'ESSAI GRATUIT fait entendre son message APRÈS « Valider ma séance »
            (« Ton essai est prêt »), jamais sur cette première page. */}
        {audio && type !== 'trial' && type !== 'event_paid' ? <div style={{ margin: '0 0 14px' }}><MotAudio url={audio} prenom={prenom} inerte={enApercu} /></div> : null}
      </main>

      {type === 'event_paid' ? null : <div style={{ position: enApercu ? 'sticky' : 'fixed', left: 0, right: 0, bottom: 0, padding: '12px 16px calc(12px + env(safe-area-inset-bottom, 0px))', background: 'linear-gradient(180deg, rgba(8,4,12,0) 0%, rgba(8,4,12,0.95) 40%)' }}>
        {envoi.erreur ? (
          <p data-testid="inv-pub-cta-erreur" role="alert" style={{ maxWidth: COLONNE_INTERIEURE, margin: '0 auto 8px', fontSize: '13.5px', color: 'rgba(255,190,180,1)', textAlign: 'center' }}>{envoi.erreur}</p>
        ) : null}
        <button type="button" onClick={surCta} data-testid="inv-pub-cta" disabled={envoi.cours}
                style={{ display: 'block', width: '100%', maxWidth: COLONNE_INTERIEURE, margin: '0 auto', minHeight: '52px', borderRadius: '999px', border: 'none',
                  background: PRIMAIRE, color: 'rgba(255,255,255,1)', fontSize: '17px', fontWeight: 800, cursor: 'pointer', opacity: envoi.cours ? 0.75 : 1 }}>
          {envoi.cours ? 'Ouverture du paiement…' : (String(d.cta_label || '').trim() || 'Continuer')}
        </button>
      </div>}
    </div>
  );
}

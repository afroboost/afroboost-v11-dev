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

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;

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

/** « jusqu'au samedi 24 octobre, 20:00 » (heure suisse). */
function dateBascule(iso) {
  try {
    return new Intl.DateTimeFormat('fr-CH', { weekday: 'long', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Zurich' })
      .format(new Date(iso));
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

function MotAudio({ url, prenom }) {
  const ref = useRef(null);
  const [lecture, setLecture] = useState(false);
  const basculer = () => {
    const a = ref.current;
    if (!a) return;
    if (a.paused) { const p = a.play(); if (p && p.catch) p.catch(() => setLecture(false)); setLecture(true); } else { a.pause(); setLecture(false); }
  };
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 14px', borderRadius: '14px', background: rgbaP(0.1), border: `1px solid ${rgbaP(0.3)}` }}>
      <button type="button" onClick={basculer} data-testid="inv-pub-audio" aria-label={lecture ? 'Mettre en pause' : 'Écouter'}
              style={{ width: '44px', height: '44px', borderRadius: '999px', border: 'none', background: PRIMAIRE, color: 'rgba(255,255,255,1)',
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flex: 'none' }}>
        {lecture ? (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" />
          </svg>
        ) : <SvgIcon name="play" size={18} />}
      </button>
      <div style={{ fontSize: '14px', color: 'rgba(255,255,255,0.9)' }}>
        <div style={{ fontWeight: 700 }}>{prenom ? `Un mot de ${prenom}` : 'Un mot pour toi'}</div>
        <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: '12.5px' }}>{lecture ? 'En lecture' : 'Écouter'}</div>
      </div>
      <audio ref={ref} src={url} preload="none" onEnded={() => setLecture(false)} onPause={() => setLecture(false)} />
    </div>
  );
}

export default function InvitationPublique({ token }) {
  const [etat, setEtat] = useState({ charge: true, d: null, erreur: false });
  const suiviRef = useRef(false);

  useEffect(() => {
    let vivant = true;
    fetch(`${BACKEND_URL}/api/invitation/publique/${encodeURIComponent(token)}`, { headers: { Accept: 'application/json' } })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => { if (vivant) setEtat({ charge: false, d, erreur: false }); })
      .catch(() => { if (vivant) setEtat({ charge: false, d: null, erreur: true }); });
    return () => { vivant = false; };
  }, [token]);

  useEffect(() => {
    if (!etat.d || suiviRef.current) return;
    suiviRef.current = true;
    suivreInvitation(token, 'lien_ouvert');
  }, [etat.d, token]);

  const cadre = { minHeight: '100vh', background: 'rgb(8,4,12)', color: 'rgba(255,255,255,0.96)', fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif' };
  if (etat.charge) return <div style={cadre} data-testid="inv-pub-chargement" />;
  if (etat.erreur || !etat.d) {
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

  const d = etat.d;
  const inv = d.inviter_display || {};
  const prenom = String(inv.prenom || '').trim();
  const photo = urlSure(inv.photo_url);
  const video = urlSure(d.video_url);
  const audio = urlSure(d.audio_url);
  const image = urlSure(d.image_url) || urlSure(d.card_url);
  const pa = d.prix_actif || null;
  const type = d.type;
  const titre = type === 'trial' ? (prenom ? `${prenom} t'invite à découvrir Afroboost` : 'Découvre Afroboost')
    : (String(d.title || d.offre_nom || '').trim() || 'Invitation Afroboost');
  const surCta = () => {
    suivreInvitation(token, 'reservation_commencee');
    window.location.href = cibleSure(d.cible);
  };

  return (
    <div style={cadre} data-testid="inv-pub">
      <main style={{ maxWidth: '560px', margin: '0 auto', padding: '20px 16px 120px', boxSizing: 'border-box' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
          {photo ? <img src={photo} alt="" width="44" height="44" style={{ width: '44px', height: '44px', borderRadius: '999px', objectFit: 'cover', border: `2px solid ${PRIMAIRE}` }} />
            : <span style={{ width: '44px', height: '44px', borderRadius: '999px', background: rgbaP(0.25), display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: PRIMAIRE }}><SvgIcon name="user" size={20} /></span>}
          <div data-testid="inv-pub-inviteur" style={{ fontSize: '15px', fontWeight: 700 }}>{prenom ? `${prenom} t'invite` : "On t'invite"}</div>
        </div>

        {(video || image) ? (
        <div style={{ borderRadius: '16px', overflow: 'hidden', background: rgbaP(0.08), border: `1px solid ${rgbaP(0.25)}`, marginBottom: '16px' }}>
          {video ? (
            // Jamais de lecture automatique : poster + contrôles (lecture, pause, son).
            <video data-testid="inv-pub-video" src={video} poster={image || undefined} controls playsInline preload="none"
                   style={{ display: 'block', width: '100%', maxHeight: '70vh', background: 'rgb(0,0,0)' }} />
          ) : (image ? (
            <img data-testid="inv-pub-image" src={image} alt={titre} loading="lazy" width="1200" height="630"
                 style={{ display: 'block', width: '100%', height: 'auto', aspectRatio: '1200 / 630', objectFit: 'cover' }} />
          ) : null)}
        </div>
        ) : null}

        <h1 data-testid="inv-pub-titre" style={{ fontSize: '26px', lineHeight: 1.2, margin: '0 0 8px' }}>{titre}</h1>
        {d.subtitle ? <p style={{ color: 'rgba(255,255,255,0.78)', margin: '0 0 12px', fontSize: '15px' }}>{d.subtitle}</p> : null}
        {type === 'trial' ? (
          <p data-testid="inv-pub-pitch" style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'rgba(255,255,255,0.85)', margin: '0 0 14px', fontSize: '15px' }}>
            <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="headphones" size={18} /></span>
            Cardio + danse afro + casques immersifs, cours d'1 h.
          </p>
        ) : null}

        <div style={{ display: 'grid', gap: '8px', margin: '0 0 16px' }}>
          {d.date_label ? <Ligne icone="calendar" testid="inv-pub-date">{maj(d.date_label)}</Ligne> : null}
          {d.time_label ? <Ligne icone="clock" testid="inv-pub-heure">{d.time_label}</Ligne> : null}
          {d.lieu ? <Ligne icone="mapPin" testid="inv-pub-lieu">{d.lieu}</Ligne> : null}
        </div>

        {type === 'trial' ? (
          <div data-testid="inv-pub-offert" style={{ padding: '12px 14px', borderRadius: '14px', background: rgbaP(0.14), border: `1px solid ${rgbaP(0.4)}`, margin: '0 0 16px', display: 'flex', alignItems: 'center', gap: '10px', fontWeight: 700 }}>
            <span style={{ color: PRIMAIRE, display: 'inline-flex' }}><SvgIcon name="gift" size={20} /></span> Ton premier cours est offert
          </div>
        ) : null}
        {type === 'event_free' ? (
          <div data-testid="inv-pub-gratuit" style={{ padding: '12px 14px', borderRadius: '14px', background: rgbaP(0.14), border: `1px solid ${rgbaP(0.4)}`, margin: '0 0 16px', fontWeight: 700 }}>
            Gratuit — inscription libre
          </div>
        ) : null}
        {type === 'event_paid' && pa ? (
          <div data-testid="inv-pub-prix" style={{ padding: '14px', borderRadius: '14px', background: rgbaP(0.12), border: `1px solid ${rgbaP(0.4)}`, margin: '0 0 16px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', flexWrap: 'wrap' }}>
              <span data-testid="inv-pub-prix-actif" style={{ fontSize: '28px', fontWeight: 800 }}>{prixTexte(pa.prix)}</span>
              {pa.palier !== 'regular' ? <span style={{ fontSize: '14px', color: 'rgba(255,255,255,0.8)' }}>{pa.libelle}</span> : null}
            </div>
            {pa.paliers && pa.paliers.length > 1 ? (
              <div style={{ display: 'grid', gridTemplateColumns: `repeat(${pa.paliers.length}, 1fr)`, gap: '6px', marginTop: '10px' }}>
                {pa.paliers.map((p) => (
                  <div key={p.palier} data-testid={`inv-pub-palier-${p.palier}`} data-actif={p.actif ? '1' : '0'}
                       style={{ padding: '6px 4px', borderRadius: '10px', textAlign: 'center', opacity: p.actif ? 1 : 0.55,
                         background: p.actif ? rgbaP(0.25) : 'rgba(255,255,255,0.05)', border: p.actif ? `1px solid ${PRIMAIRE}` : '1px solid transparent' }}>
                    <div style={{ fontSize: '11.5px', color: 'rgba(255,255,255,0.8)' }}>{p.libelle}</div>
                    <div style={{ fontSize: '15px', fontWeight: 700 }}>{prixTexte(p.prix)}</div>
                  </div>
                ))}
              </div>
            ) : null}
            {pa.prochain ? (
              <p data-testid="inv-pub-urgence" style={{ margin: '10px 0 0', fontSize: '13.5px', color: 'rgba(255,255,255,0.85)' }}>
                Plus tu réserves tôt, moins c'est cher : {prixTexte(pa.prochain.prix)} à partir du {dateBascule(pa.prochain.a_partir_de)}.
              </p>
            ) : null}
            {d.gratuit_membres ? (
              /* V610 : la gratuité est décidée par le serveur (abonnement 8 mois actif), jamais ici. */
              <p data-testid="inv-pub-gratuit-membres" style={{ margin: '8px 0 0', fontSize: '13.5px', fontWeight: 600, color: 'var(--primary-color, #D91CD2)' }}>
                Offert si tu as un abonnement Afroboost 8 mois actif.
              </p>
            ) : null}
          </div>
        ) : null}

        {d.message ? (
          <p data-testid="inv-pub-message" style={{ margin: '0 0 16px', padding: '12px 14px', borderRadius: '14px', background: 'rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.88)', fontSize: '15px', whiteSpace: 'pre-line' }}>
            {d.message}
          </p>
        ) : null}
        {audio ? <div style={{ margin: '0 0 16px' }}><MotAudio url={audio} prenom={prenom} /></div> : null}
      </main>

      <div style={{ position: 'fixed', left: 0, right: 0, bottom: 0, padding: '12px 16px calc(12px + env(safe-area-inset-bottom, 0px))', background: 'linear-gradient(180deg, rgba(8,4,12,0) 0%, rgba(8,4,12,0.95) 40%)' }}>
        <button type="button" onClick={surCta} data-testid="inv-pub-cta"
                style={{ display: 'block', width: '100%', maxWidth: '560px', margin: '0 auto', minHeight: '52px', borderRadius: '999px', border: 'none',
                  background: PRIMAIRE, color: 'rgba(255,255,255,1)', fontSize: '17px', fontWeight: 800, cursor: 'pointer' }}>
          {String(d.cta_label || '').trim() || (type === 'event_paid' ? 'Je réserve ma place' : 'Continuer')}
        </button>
      </div>
    </div>
  );
}

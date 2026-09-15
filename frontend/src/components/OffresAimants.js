/**
 * OFFRES AIMANTS — le parcours de conversion du visiteur NON connecté.
 *
 * Trois cartes (lancement, saison 8 mois, mensuel de référence), un bouton
 * « Voir toutes les offres » (panneau liste), et UNE fiche détail par offre
 * (modale desktop / feuille basse mobile). La fiche est le seul endroit où
 * toutes les informations s'affichent ; les cartes restent sobres.
 *
 * AUCUN nouveau tunnel : le bouton de la fiche appelle `onChoisir(offre)`, qui
 * est `handleSelectOffer` d'App.js — le même point d'entrée que le carrousel
 * historique (achat direct Stripe pour le payant, formulaire pour le gratuit,
 * grille de dates pour l'avantage membre). Le paiement Mobile Money garde son
 * bouton existant (`PawaPayOfferButton`). L'attribution partenaire (UTM,
 * cookie serveur) n'est pas touchée : elle voyage avec la requête de checkout.
 *
 * Les décisions (familles, badges, économies, libellés) viennent de
 * utils/offresAimants.js, testé à part. Ici : uniquement du rendu.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import SvgIcon from './SvgIcon';
import PawaPayOfferButton from './PawaPayOfferButton';
import useLargeurEcran from '../utils/useLargeurEcran';
import {
  regrouperOffres, ficheOffre, badgeOffre, prixAffiche, libelleSeances, infoCompacteLimitee,
  libelleDepuis, prixUnitaire, prixFormate, economieOffre, libellePaiement, familleOffre, FAMILLE, promesseCourte,
} from '../utils/offresAimants';
import { stylesLecteur, normaliserRatio, ratioDepuisDimensions } from '../utils/videoRatio';
import { mediaPrincipal } from '../utils/mediaOffre';
import { trimDeLOffre, useTrimVideo } from '../utils/videoTrim';

const COULEUR = 'var(--primary-color, #D91CD2)';
const RGB = 'var(--primary-rgb, 217, 28, 210)';
const FOND_CARTE = 'linear-gradient(180deg, rgba(20,10,30,0.98) 0%, rgba(5,0,15,0.99) 100%)';

const ICONE_AIMANT = { lancement: 'fire', saison: 'star', mensuel: 'zap' };

/* ───────────────────────── média d'une offre ───────────────────────── */

/**
 * RÈGLE DE RENDU MÉDIA (carte + fiche = remplissage, agrandi = format réel) :
 *  - sur la carte et dans la fiche, le média REMPLIT son cadre (`cover`,
 *    centré) — un vrai bloc visuel, pas un bâton vertical au milieu du vide ;
 *  - le cadre de la fiche prend une forme proche du média (portrait → 4:5,
 *    carré → 1:1, paysage → 16:9) pour rogner le moins possible ;
 *  - « Agrandir » (et le plein écran natif, CSS `video:fullscreen`) montre le
 *    format RÉEL du fichier : 9:16 vertical, 16:9 horizontal, 1:1 carré, en
 *    `contain`, jamais déformé ni rogné.
 */
const cadreFiche = (ratio, mesure, estMobile) => {
  const r = normaliserRatio(ratio);
  const portrait = r === '9:16' || (r === 'auto' && !!mesure && mesure.h > mesure.w);
  const carre = r === '1:1' || (r === 'auto' && !!mesure && Math.abs(mesure.w / mesure.h - 1) <= 0.08);
  if (portrait) return { aspectRatio: '4 / 5', maxHeight: estMobile ? '64vh' : '56vh' };
  if (carre) return { aspectRatio: '1 / 1', maxHeight: estMobile ? '60vh' : '52vh' };
  return { aspectRatio: '16 / 9', maxHeight: estMobile ? '40vh' : '48vh' };
};

/** Bouton « Agrandir » posé sur le cadre. */
function BoutonAgrandir({ onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Agrandir le média"
      data-testid="fiche-agrandir"
      style={{ position: 'absolute', right: 10, bottom: 10, zIndex: 3, width: 36, height: 36, borderRadius: 18, border: '1px solid rgba(255,255,255,0.25)', background: 'rgba(0,0,0,0.55)', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
    >
      <SvgIcon name="externalLink" size={16} />
    </button>
  );
}

/**
 * Le média AGRANDI : format réel du fichier. Image entière ; vidéo en
 * `contain` au ratio stocké/mesuré (9:16 reste vertical, 16:9 horizontal,
 * 1:1 carré), avec ses contrôles natifs (le plein écran garde ce rendu).
 */
function MediaAgrandi({ offre, poster, video, ratio, onFermer }) {
  const videoRef = useRef(null);
  useTrimVideo(videoRef, trimDeLOffre(offre), { loop: false });
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onFermer(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onFermer]);
  if (typeof document === 'undefined') return null;
  const st = stylesLecteur(ratio, { hauteurMax: '88vh', fond: 'transparent' });
  return createPortal(
    <div role="dialog" aria-modal="true" aria-label="Média en grand" data-testid="media-agrandi" data-ratio={ratio}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onFermer(); }}
      style={{ position: 'fixed', inset: 0, zIndex: 1300, background: 'rgba(0,0,0,0.92)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 12 }}>
      <button type="button" onClick={onFermer} aria-label="Fermer" data-testid="media-agrandi-fermer"
        style={{ position: 'absolute', top: 12, right: 12, width: 40, height: 40, borderRadius: 20, border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.08)', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
        <SvgIcon name="x" size={18} />
      </button>
      {video ? (
        <video ref={videoRef} src={video} poster={poster || undefined} controls autoPlay playsInline preload="metadata" style={{ ...st.video, maxWidth: '96vw' }} />
      ) : (
        <img src={poster} alt={offre.name || ''} style={{ maxWidth: '96vw', maxHeight: '88vh', objectFit: 'contain', display: 'block' }} />
      )}
    </div>,
    document.body,
  );
}

/**
 * Le média de la fiche : REMPLIT son cadre (cover), fond flouté derrière
 * pendant le chargement, « Agrandir » pour le format réel. La vidéo joue
 * l'extrait découpé (même hook que la vitrine et le plein écran).
 */
function LecteurOffre({ offre, analyser, estMobile }) {
  const [mesure, setMesure] = useState(null);
  const [videoKo, setVideoKo] = useState(false);
  const [imageKo, setImageKo] = useState(false);
  const [agrandi, setAgrandi] = useState(false);
  const videoRef = useRef(null);
  useTrimVideo(videoRef, trimDeLOffre(offre), { loop: false });
  const { poster, video } = mediaPrincipal(offre, analyser);
  const ratioStocke = normaliserRatio(offre.video_aspect_ratio);
  const ratio = ratioStocke !== 'auto' ? ratioStocke : (mesure ? ratioDepuisDimensions(mesure.w, mesure.h) : 'auto');
  const cadre = cadreFiche(ratio, mesure, estMobile);
  const trim = trimDeLOffre(offre);
  const conteneur = { position: 'relative', width: '100%', overflow: 'hidden', background: 'var(--video-bg, #000)', ...cadre };
  const plein = { position: 'relative', zIndex: 1, width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center', display: 'block' };
  const aVideo = !!video && !videoKo;
  const aImage = !!poster && !imageKo;
  if (!aVideo && !aImage) {
    // Repli : aucune zone vide cassée, un bandeau de marque sobre.
    return <div style={{ height: 96, background: `linear-gradient(135deg, rgba(${RGB}, 0.35), rgba(139, 92, 246, 0.25))` }} data-testid="fiche-repli" />;
  }
  return (
    <>
      <div style={conteneur} data-testid={aVideo ? 'fiche-lecteur' : 'fiche-image'} data-ratio={ratio}>
        <FondFlou poster={poster} />
        {aVideo ? (
          <video
            ref={videoRef}
            src={video}
            poster={poster || undefined}
            controls
            playsInline
            preload="metadata"
            data-trim={trim ? `${trim.start}-${trim.end}` : ''}
            style={plein}
            onLoadedMetadata={(e) => {
              const v = e.currentTarget;
              if (v.videoWidth && v.videoHeight) setMesure({ w: v.videoWidth, h: v.videoHeight });
            }}
            onError={() => setVideoKo(true)}
          />
        ) : (
          <img src={poster} alt={offre.name || ''} onError={() => setImageKo(true)} style={plein}
            onLoad={(e) => { const i = e.currentTarget; if (i.naturalWidth && i.naturalHeight) setMesure({ w: i.naturalWidth, h: i.naturalHeight }); }} />
        )}
        <BoutonAgrandir onClick={() => setAgrandi(true)} />
      </div>
      {agrandi ? <MediaAgrandi offre={offre} poster={poster} video={aVideo ? video : ''} ratio={ratio} onFermer={() => setAgrandi(false)} /> : null}
    </>
  );
}

/**
 * Fond flouté derrière un média : la zone est « remplie » visuellement
 * pendant le chargement. Poster flouté s'il existe, sinon le dégradé de marque.
 */
function FondFlou({ poster }) {
  const style = {
    position: 'absolute', inset: 0, zIndex: 0,
    background: poster ? `center / cover no-repeat url("${poster}")` : `linear-gradient(135deg, rgba(${RGB}, 0.35), rgba(139, 92, 246, 0.25))`,
    filter: poster ? 'blur(18px) brightness(0.55)' : 'none',
    transform: 'scale(1.15)',
  };
  return <div aria-hidden="true" style={style} data-testid="fond-flou" />;
}

/**
 * La vignette d'une carte : la MINIATURE (image) remplit la zone ; sans image,
 * la vidéo muette remplit la zone (cover, centrée) et joue l'extrait découpé.
 * Sans rien, ou média indisponible : repli sobre.
 */
function VignetteOffre({ offre, analyser, hauteur }) {
  const [videoKo, setVideoKo] = useState(false);
  const [imageKo, setImageKo] = useState(false);
  const videoRef = useRef(null);
  useTrimVideo(videoRef, trimDeLOffre(offre), { loop: true });
  const { poster, video } = mediaPrincipal(offre, analyser);
  const h = hauteur || 170;
  const repli = <div style={{ width: '100%', height: h, background: `linear-gradient(135deg, rgba(${RGB}, 0.35), rgba(139, 92, 246, 0.25))` }} data-testid="vignette-repli" />;
  if (poster && !imageKo) {
    return <img src={poster} alt="" onError={() => setImageKo(true)} style={{ width: '100%', height: h, objectFit: 'cover', objectPosition: 'center', display: 'block' }} data-testid="vignette-image" />;
  }
  if (!video || videoKo) return repli;
  return (
    <div style={{ position: 'relative', width: '100%', height: h, overflow: 'hidden', background: 'var(--video-bg, #000)' }} data-testid="vignette-video">
      <video
        ref={videoRef}
        src={video}
        muted
        autoPlay
        loop
        playsInline
        preload="metadata"
        style={{ position: 'relative', zIndex: 1, width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center', display: 'block' }}
        onError={() => setVideoKo(true)}
      />
    </div>
  );
}

/* ───────────────────────── panneau (modale / feuille) ───────────────────────── */

function Panneau({ ouvert, onFermer, titre, children, estMobile, testId }) {
  useEffect(() => {
    if (!ouvert) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') onFermer(); };
    document.addEventListener('keydown', onKey);
    const avant = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = avant; };
  }, [ouvert, onFermer]);
  if (!ouvert || typeof document === 'undefined') return null;
  const feuille = estMobile;
  return createPortal(
    <div
      role="presentation"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onFermer(); }}
      style={{
        position: 'fixed', inset: 0, zIndex: 1200, background: 'rgba(0,0,0,0.72)',
        display: 'flex', alignItems: feuille ? 'flex-end' : 'center', justifyContent: 'center',
        backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)',
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={titre}
        data-testid={testId}
        style={{
          width: feuille ? '100%' : 'min(560px, 92vw)',
          maxHeight: feuille ? '92vh' : '90vh',
          overflowY: 'auto',
          background: FOND_CARTE,
          color: '#fff',
          borderRadius: feuille ? '20px 20px 0 0' : '20px',
          boxShadow: `0 0 0 1px rgba(${RGB}, 0.35), 0 20px 60px rgba(0,0,0,0.6)`,
          paddingBottom: feuille ? 'max(16px, env(safe-area-inset-bottom))' : 0,
          animation: feuille ? 'aimantsMonter 0.25s ease-out' : 'aimantsApparaitre 0.2s ease-out',
        }}
      >
        <div style={{ position: 'sticky', top: 0, zIndex: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', background: 'rgba(8,2,16,0.92)', backdropFilter: 'blur(8px)', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          {feuille ? <span aria-hidden="true" style={{ position: 'absolute', top: 6, left: '50%', transform: 'translateX(-50%)', width: 40, height: 4, borderRadius: 2, background: 'rgba(255,255,255,0.25)' }} /> : null}
          <span style={{ fontSize: 13, fontWeight: 600, color: 'rgba(255,255,255,0.7)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>{titre}</span>
          <button
            type="button"
            onClick={onFermer}
            aria-label="Fermer"
            data-testid="panneau-fermer"
            style={{ width: 36, height: 36, borderRadius: 18, border: '1px solid rgba(255,255,255,0.15)', background: 'rgba(255,255,255,0.06)', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
          >
            <SvgIcon name="x" size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

/* ───────────────────────── badge ───────────────────────── */

function Badge({ texte, fort }) {
  if (!texte) return null;
  return (
    <span
      data-testid="badge-offre"
      style={{
        display: 'inline-block', fontSize: 11, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase',
        padding: '3px 10px', borderRadius: 999,
        background: fort ? COULEUR : `rgba(${RGB}, 0.18)`,
        color: fort ? '#fff' : COULEUR,
        border: `1px solid rgba(${RGB}, 0.5)`,
      }}
    >
      {texte}
    </span>
  );
}

/* ───────────────────────── fiche détail ───────────────────────── */

function LigneFiche({ icone, libelle, valeur }) {
  if (!valeur) return null;
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
      <span style={{ color: COULEUR, flexShrink: 0, marginTop: 2 }}><SvgIcon name={icone} size={16} /></span>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{libelle}</div>
        <div style={{ fontSize: 14, color: '#fff' }}>{valeur}</div>
      </div>
    </div>
  );
}

function FicheOffre({ choix, mensuelRef, analyser, onChoisir, onFermer, checkoutBusy, estMobile, Countdown }) {
  // `choix` = { offres: [...] } — 1 offre, ou les 2 offres de la saison.
  const offres = (choix && choix.offres) || [];
  const [selection, setSelection] = useState(offres[0] ? offres[0].id : null);
  useEffect(() => { setSelection(offres[0] ? offres[0].id : null); }, [choix]); // eslint-disable-line react-hooks/exhaustive-deps
  const offre = offres.find((o) => o.id === selection) || offres[0];
  const fiche = useMemo(() => ficheOffre(offre, mensuelRef), [offre, mensuelRef]);
  if (!choix || !offre || !fiche) return null;
  const groupeSaison = offres.length > 1;
  const titre = groupeSaison ? 'Saison 8 mois' : fiche.nom;
  const payant = !fiche.gratuit;
  return (
    <Panneau ouvert onFermer={onFermer} titre="Détail de l’offre" estMobile={estMobile} testId="fiche-offre">
      <LecteurOffre offre={offre} analyser={analyser} estMobile={estMobile} />
      <div style={{ padding: '14px 18px 18px' }}>
        <Badge texte={groupeSaison ? 'Meilleur prix' : fiche.badge} fort={fiche.famille === FAMILLE.LANCEMENT} />
        <h3 style={{ fontSize: 22, fontWeight: 800, margin: '8px 0 2px', color: '#fff' }} data-testid="fiche-nom">{titre}</h3>
        {!groupeSaison ? (
          <p style={{ margin: 0, fontSize: 26, fontWeight: 900, color: COULEUR }} data-testid="fiche-prix">
            {fiche.prix.montant}{fiche.prix.unite ? <span style={{ fontSize: 14, color: 'rgba(255,255,255,0.6)', fontWeight: 500 }}> {fiche.prix.unite}</span> : null}
          </p>
        ) : (
          <p style={{ margin: 0, fontSize: 20, fontWeight: 800, color: COULEUR }} data-testid="fiche-prix">
            {libelleDepuis({ cle: 'saison', depuis: Math.min(...offres.map((o) => (familleOffre(o) === FAMILLE.SAISON_2X ? prixUnitaire(o) * 2 : prixUnitaire(o)))) })}
          </p>
        )}
        {fiche.promesse ? <p style={{ margin: '8px 0 0', fontSize: 15, color: 'rgba(255,255,255,0.85)' }}>{fiche.promesse}</p> : null}
        {fiche.limitee ? <p style={{ margin: '8px 0 0', fontSize: 13, color: '#fff', fontWeight: 600 }} data-testid="fiche-limitee">{fiche.limitee}</p> : null}
        {!groupeSaison && Countdown && familleOffre(offre) === FAMILLE.LANCEMENT ? <Countdown offer={offre} /> : null}

        {groupeSaison ? (
          <div role="radiogroup" aria-label="Mode de paiement" style={{ marginTop: 14, display: 'grid', gap: 8 }} data-testid="fiche-choix-saison">
            {offres.map((o) => {
              const actif = o.id === selection;
              const p = prixAffiche(o);
              const eco = economieOffre(o, mensuelRef);
              return (
                <label
                  key={o.id}
                  data-testid={`choix-saison-${o.id}`}
                  style={{
                    display: 'flex', gap: 12, alignItems: 'flex-start', padding: '12px 14px', borderRadius: 12, cursor: 'pointer',
                    border: `1px solid ${actif ? COULEUR : 'rgba(255,255,255,0.14)'}`,
                    background: actif ? `rgba(${RGB}, 0.14)` : 'rgba(255,255,255,0.04)',
                  }}
                >
                  <input type="radio" name="saison-choix" checked={actif} onChange={() => setSelection(o.id)} style={{ accentColor: COULEUR, marginTop: 4 }} />
                  <span style={{ minWidth: 0 }}>
                    <span style={{ display: 'block', fontWeight: 800, fontSize: 16, color: '#fff' }}>{p.montant}{p.unite ? <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)', fontWeight: 500 }}> {p.unite}</span> : null}</span>
                    <span style={{ display: 'block', fontSize: 13, color: 'rgba(255,255,255,0.75)' }}>{familleOffre(o) === FAMILLE.SAISON_2X ? 'Paiement en deux fois' : 'Paiement en une fois'} — {libellePaiement(o)}</span>
                    {eco ? <span style={{ display: 'block', fontSize: 13, color: 'var(--eco-color, #8ef0b0)', fontWeight: 700, marginTop: 2 }}>Tu économises {prixFormate(eco)} CHF par rapport au mensuel</span> : null}
                  </span>
                </label>
              );
            })}
          </div>
        ) : null}

        {fiche.inclus.length ? (
          <ul style={{ listStyle: 'none', padding: 0, margin: '14px 0 4px', display: 'grid', gap: 6 }} data-testid="fiche-inclus">
            {fiche.inclus.map((l) => (
              <li key={l} style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 14, color: '#fff' }}>
                <span style={{ color: COULEUR, display: 'inline-flex' }}><SvgIcon name="check" size={16} /></span>{l}
              </li>
            ))}
          </ul>
        ) : null}

        <div style={{ marginTop: 6 }}>
          <LigneFiche icone="calendar" libelle="Durée" valeur={fiche.duree} />
          <LigneFiche icone="creditCard" libelle="Paiement" valeur={groupeSaison ? libellePaiement(offre) : fiche.paiement} />
          <LigneFiche icone="lock" libelle="Engagement" valeur={fiche.engagement} />
          <LigneFiche icone="info" libelle="Conditions" valeur={fiche.conditions.length ? fiche.conditions.join(' · ') : ''} />
          <LigneFiche icone="users" libelle="Pour qui" valeur={fiche.pourQui} />
        </div>
        {!groupeSaison && fiche.economie ? <p style={{ margin: '10px 0 0', fontSize: 14, fontWeight: 700, color: 'var(--eco-color, #8ef0b0)' }} data-testid="fiche-economie">{fiche.economie}</p> : null}

        <button
          type="button"
          data-testid="fiche-cta"
          disabled={!!checkoutBusy}
          onClick={() => { onFermer(); onChoisir(offre); }}
          style={{
            marginTop: 16, width: '100%', padding: '14px 18px', borderRadius: 999, border: 'none', cursor: checkoutBusy ? 'wait' : 'pointer',
            background: COULEUR, color: '#fff', fontWeight: 800, fontSize: 16,
            boxShadow: `0 6px 24px rgba(${RGB}, 0.45)`, opacity: checkoutBusy ? 0.7 : 1,
          }}
        >
          {fiche.gratuit ? 'Réserver mon 1er cours gratuit' : 'Choisir cette formule'}
        </button>
        {payant ? (
          <div style={{ marginTop: 10, display: 'flex', justifyContent: 'center' }}>
            <PawaPayOfferButton offer={offre} priceChf={prixUnitaire(offre)} disabled={!!checkoutBusy} />
          </div>
        ) : null}
      </div>
    </Panneau>
  );
}

/* ───────────────────────── toutes les offres ───────────────────────── */

const GROUPES = [
  { cle: 'lancement', titre: 'Offre de lancement', familles: [FAMILLE.LANCEMENT] },
  { cle: 'saison', titre: 'La saison', familles: [FAMILLE.SAISON_1X, FAMILLE.SAISON_2X] },
  { cle: 'mensuel', titre: 'Chaque mois, sans engagement', familles: [FAMILLE.MENSUEL] },
  { cle: 'unite', titre: 'À l’unité', familles: [FAMILLE.UNITE] },
  { cle: 'membre', titre: 'Association', familles: [FAMILLE.MEMBRE] },
  { cle: 'offert', titre: 'Pour découvrir', familles: [FAMILLE.OFFERT] },
];

/** Petite vignette carrée (miniature ou première image de la vidéo). */
function MiniVignette({ offre, analyser }) {
  const { poster, video } = mediaPrincipal(offre, analyser);
  const base = { width: 56, height: 56, borderRadius: 12, flexShrink: 0, objectFit: 'cover', display: 'block', background: `rgba(${RGB}, 0.18)` };
  if (poster) return <img src={poster} alt="" style={base} />;
  if (video) return <video src={video} muted playsInline preload="metadata" style={base} />;
  return <div style={{ ...base, display: 'flex', alignItems: 'center', justifyContent: 'center', color: COULEUR }}><SvgIcon name="gift" size={20} /></div>;
}

function ToutesLesOffres({ ouvert, offres, mensuelRef, analyser, onOuvrirFiche, onFermer, estMobile }) {
  const groupes = GROUPES.map((g) => ({ ...g, offres: offres.filter((o) => g.familles.includes(familleOffre(o))) })).filter((g) => g.offres.length);
  return (
    <Panneau ouvert={ouvert} onFermer={onFermer} titre="Toutes les offres" estMobile={estMobile} testId="toutes-les-offres">
      <div style={{ padding: '6px 12px 12px' }} data-testid="liste-toutes-offres">
        {groupes.map((g) => (
          <section key={g.cle} data-testid={`groupe-${g.cle}`} style={{ marginTop: 10 }}>
            <h4 style={{ margin: '8px 4px 6px', fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'rgba(255,255,255,0.45)' }}>{g.titre}</h4>
            {/* `minmax(0, 1fr)` : sans lui, une ligne à contenu long élargit la
                grille (min-width: auto des items) et le prix sort de l'écran. */}
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gap: 8 }}>
              {g.offres.map((o) => {
                const p = prixAffiche(o);
                const badge = badgeOffre(o, mensuelRef);
                const fam = familleOffre(o);
                const seances = libelleSeances(o);
                const limitee = infoCompacteLimitee(o);
                const eco = economieOffre(o, mensuelRef);
                const sousTitre = [seances, limitee].filter(Boolean).join(' · ') || promesseCourte(o);
                return (
                  <li key={o.id} style={{ minWidth: 0 }}>
                    <button
                      type="button"
                      data-testid={`ligne-offre-${o.id}`}
                      onClick={() => onOuvrirFiche({ offres: [o] })}
                      style={{
                        width: '100%', maxWidth: '100%', textAlign: 'left', display: 'block', overflow: 'hidden',
                        padding: '10px 12px', borderRadius: 14, cursor: 'pointer', color: '#fff',
                        background: fam === FAMILLE.LANCEMENT ? `rgba(${RGB}, 0.10)` : 'rgba(255,255,255,0.04)',
                        border: `1px solid ${fam === FAMILLE.LANCEMENT ? `rgba(${RGB}, 0.45)` : 'rgba(255,255,255,0.08)'}`,
                        transition: 'background 0.15s, border-color 0.15s',
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.background = `rgba(${RGB}, 0.14)`; e.currentTarget.style.borderColor = `rgba(${RGB}, 0.5)`; }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = fam === FAMILLE.LANCEMENT ? `rgba(${RGB}, 0.10)` : 'rgba(255,255,255,0.04)'; e.currentTarget.style.borderColor = fam === FAMILLE.LANCEMENT ? `rgba(${RGB}, 0.45)` : 'rgba(255,255,255,0.08)'; }}
                    >
                      {/* Un conteneur flex DANS le bouton : un <button> en flex ne
                          laisse pas toujours ses enfants rétrécir, le prix sortait
                          de l'écran sur mobile. */}
                      <span style={{ display: 'flex', gap: 12, alignItems: 'center', width: '100%', minWidth: 0 }}>
                        <MiniVignette offre={o} analyser={analyser} />
                        <span style={{ minWidth: 0, flex: '1 1 0%', display: 'flex', flexDirection: 'column', gap: 3, overflow: 'hidden' }}>
                          <span style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                            <span style={{ fontWeight: 700, fontSize: 15, lineHeight: 1.2 }}>{o.name}</span>
                            {badge ? <Badge texte={badge} fort={fam === FAMILLE.LANCEMENT} /> : null}
                          </span>
                          {sousTitre ? <span style={{ display: 'block', fontSize: 12, color: 'rgba(255,255,255,0.6)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{sousTitre}</span> : null}
                          {eco ? <span style={{ display: 'block', fontSize: 12, color: 'var(--eco-color, #8ef0b0)', fontWeight: 600 }}>Économie : {prixFormate(eco)} CHF</span> : null}
                        </span>
                        <span style={{ textAlign: 'right', flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                          <span style={{ fontWeight: 800, fontSize: 16, color: COULEUR, whiteSpace: 'nowrap' }}>{p.montant}</span>
                          {p.unite ? <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)' }}>{p.unite}</span> : null}
                        </span>
                        <span style={{ color: 'rgba(255,255,255,0.35)', display: 'inline-flex', flexShrink: 0 }}><SvgIcon name="arrowRight" size={14} /></span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </Panneau>
  );
}

/* ───────────────────────── carte aimant ───────────────────────── */

function CarteAimant({ aimant, mensuelRef, analyser, onOuvrir, Countdown }) {
  const o = aimant.offre;
  const fam = familleOffre(o);
  const badge = aimant.cle === 'saison' ? 'Meilleur prix' : badgeOffre(o, mensuelRef);
  const prix = aimant.cle === 'saison' ? { montant: libelleDepuis(aimant), unite: '' } : prixAffiche(o);
  const seances = libelleSeances(o);
  const limitee = fam === FAMILLE.LANCEMENT ? infoCompacteLimitee(o) : '';
  const fort = fam === FAMILLE.LANCEMENT;
  return (
    <button
      type="button"
      data-testid={`aimant-${aimant.cle}`}
      onClick={() => onOuvrir({ offres: aimant.offres })}
      style={{
        textAlign: 'left', padding: 0, border: 'none', cursor: 'pointer', color: '#fff',
        background: FOND_CARTE, borderRadius: 16, overflow: 'hidden', display: 'flex', flexDirection: 'column',
        boxShadow: fort
          ? `0 0 0 1.5px ${COULEUR}, 0 0 18px rgba(${RGB}, 0.3)`
          : `0 0 0 1px rgba(${RGB}, 0.25), 0 4px 24px rgba(0,0,0,0.5)`,
        transition: 'transform 0.2s',
      }}
    >
      <VignetteOffre offre={o} analyser={analyser} hauteur={170} />
      <div style={{ padding: '12px 14px 14px', display: 'flex', flexDirection: 'column', gap: 6, flex: 1 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: COULEUR, display: 'inline-flex' }}><SvgIcon name={ICONE_AIMANT[aimant.cle] || 'gift'} size={16} /></span>
          <Badge texte={badge} fort={fort} />
        </span>
        <span style={{ fontSize: 18, fontWeight: 800 }}>{aimant.cle === 'saison' ? 'Saison 8 mois' : o.name}</span>
        <span style={{ fontSize: 22, fontWeight: 900, color: COULEUR }}>
          {prix.montant}{prix.unite ? <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.6)', fontWeight: 500 }}> {prix.unite}</span> : null}
        </span>
        {seances && aimant.cle !== 'saison' ? <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.7)' }}>{seances}</span> : null}
        {aimant.cle === 'saison' ? <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.7)' }}>En 1 ou 2 paiements</span> : null}
        {limitee ? <span style={{ fontSize: 12, color: '#fff', fontWeight: 600 }} data-testid="aimant-limitee">{limitee}</span> : null}
        {fort && Countdown ? <Countdown offer={o} /> : null}
        <span style={{ marginTop: 'auto', paddingTop: 6, fontSize: 14, fontWeight: 700, color: COULEUR, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          Voir l’offre <SvgIcon name="arrowRight" size={14} />
        </span>
      </div>
    </button>
  );
}

/* ───────────────────────── bloc principal ───────────────────────── */

export default function OffresAimants({ offres, analyserMedia, onChoisir, checkoutBusy, ouvrirToutesSignal, titre, Countdown }) {
  // V525: `Countdown` = le composant OfferCountdown existant d'App.js (j/h/m/s
  // dynamiques) ; aucun compteur n'est recree ici.
  const { estMobile } = useLargeurEcran();
  const analyser = typeof analyserMedia === 'function' ? analyserMedia : () => null;
  const groupe = useMemo(() => regrouperOffres(offres), [offres]);
  const [fiche, setFiche] = useState(null);
  const [toutes, setToutes] = useState(false);

  // Le bouton « Offres » de la barre de navigation ouvre le panneau : le
  // parent incrémente ce signal, on l'écoute.
  useEffect(() => { if (ouvrirToutesSignal) setToutes(true); }, [ouvrirToutesSignal]);

  // Lien profond `?offre=<id>` : la carte du carrousel n'existe plus pour un
  // visiteur, c'est la fiche qui s'ouvre. `&reserver=1` sur une offre gratuite
  // ouvre directement le formulaire (même règle que V371/V449 : jamais un
  // paiement tout seul).
  // FONDATEURS / PARCOURS (15/09/2026) — UNE SEULE FOIS. `offres` est rechargé
  // périodiquement par App : sans ce verrou, l'effet rejouait `onChoisir(o)` à
  // chaque rechargement, et `handleSelectOffer` (bascule) REFERMAIT le
  // formulaire d'essai qu'il venait d'ouvrir (mesuré : ouvert à 3 s, fermé à
  // 7 s, rouvert à 8 s). Même règle que P2-FIX2 dans App.js.
  const lienProfondTraite = useRef(false);
  useEffect(() => {
    if (!Array.isArray(offres) || !offres.length) return;
    if (lienProfondTraite.current) return;
    let cible = ''; let reserver = false;
    try {
      const q = new URLSearchParams(window.location.search);
      cible = q.get('offre') || '';
      reserver = q.get('reserver') === '1';
    } catch (e) { return; }
    if (!cible) return;
    const o = offres.find((x) => x && x.id === cible);
    if (!o) return;
    lienProfondTraite.current = true;
    if (reserver && prixUnitaire(o) <= 0) { onChoisir(o); return; }
    setFiche({ offres: [o] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offres]);

  if (!groupe.aimants.length) return null;
  const colonnes = estMobile ? '1fr' : `repeat(${Math.min(3, groupe.aimants.length)}, minmax(0, 1fr))`;
  return (
    <section data-testid="offres-aimants" style={{ marginBottom: 24 }}>
      <style>{`@keyframes aimantsMonter{from{transform:translateY(24px);opacity:.6}to{transform:none;opacity:1}}@keyframes aimantsApparaitre{from{transform:scale(.97);opacity:0}to{transform:none;opacity:1}}`}</style>
      <h2 className="font-semibold mb-3 text-white" style={{ fontSize: 18 }}>{titre || 'Nos formules'}</h2>
      <div style={{ display: 'grid', gridTemplateColumns: colonnes, gap: 12 }}>
        {groupe.aimants.map((a) => (
          <CarteAimant key={a.cle} aimant={a} mensuelRef={groupe.mensuelRef} analyser={analyser} onOuvrir={setFiche} Countdown={Countdown} />
        ))}
      </div>
      {/* Lien discret, pas un bouton massif : une petite icône + le texte. */}
      <div style={{ marginTop: 10, textAlign: 'center' }}>
        <button
          type="button"
          data-testid="voir-toutes-les-offres"
          onClick={() => setToutes(true)}
          style={{
            padding: '4px 8px', borderRadius: 6, cursor: 'pointer', border: 'none', background: 'transparent',
            color: 'rgba(255,255,255,0.75)', fontWeight: 500, fontSize: 12, lineHeight: 1.2, display: 'inline-flex', alignItems: 'center', gap: 5,
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--primary-color, #D91CD2)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = 'rgba(255,255,255,0.75)'; }}
        >
          <SvgIcon name="grid" size={12} /> Voir toutes les offres
        </button>
      </div>

      <ToutesLesOffres
        ouvert={toutes}
        offres={groupe.autres}
        mensuelRef={groupe.mensuelRef}
        analyser={analyser}
        estMobile={estMobile}
        onFermer={() => setToutes(false)}
        onOuvrirFiche={(c) => { setToutes(false); setFiche(c); }}
      />
      {fiche ? (
        <FicheOffre
          choix={fiche}
          mensuelRef={groupe.mensuelRef}
          analyser={analyser}
          onChoisir={onChoisir}
          onFermer={() => setFiche(null)}
          checkoutBusy={checkoutBusy}
          estMobile={estMobile}
          Countdown={Countdown}
        />
      ) : null}
    </section>
  );
}

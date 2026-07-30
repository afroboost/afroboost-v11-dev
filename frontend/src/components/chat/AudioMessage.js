/**
 * AudioMessage.js — V356 : lecteur de note vocale, façon messagerie moderne.
 *
 * POURQUOI UN COMPOSANT DÉDIÉ
 * Le fil affichait un `<audio controls>` brut : rendu différent sur chaque
 * navigateur, gris système, impossible à mettre aux couleurs du coach. Ce
 * composant reprend la main sur les quatre éléments demandés — bouton rond
 * lecture/pause, onde qui se remplit, temps en mm:ss, vitesse de lecture — et
 * les rend identiques partout.
 *
 * COULEUR — POINT IMPORTANT
 * Aucune couleur n'est codée en dur : tout passe par `var(--primary-color)` et
 * `var(--primary-rgb)`. Ces variables sont posées sur <html> par
 * `applyPrimaryColor()` (utils/themeColor.js) à partir de `concept.primaryColor`
 * du coach dont on visite la vitrine. Sur la vitrine du coach D, elles valent
 * donc la couleur de D ; sur la page d'accueil, celle de l'admin. Le lecteur
 * suit automatiquement, sans rien savoir du coach courant. Le `#D91CD2` des
 * `var(..., #D91CD2)` n'est qu'une valeur de secours.
 *
 * L'onde n'est PAS l'analyse du signal : décoder l'audio pour dessiner une vraie
 * forme d'onde imposerait de télécharger et décoder tout le fichier avant
 * d'afficher quoi que ce soit. On dessine des barres stables (dérivées de l'URL,
 * donc identiques d'un rendu à l'autre et d'un participant à l'autre) qui se
 * remplissent à mesure de la lecture — le repère utile est la progression.
 */
import React, { useState, useRef, useEffect, useMemo, memo } from 'react';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const VITESSES = [1, 1.5, 2];
const NB_BARRES = 28;

/** mm:ss — `00:06`. Une durée inconnue (métadonnées non chargées) rend `--:--`. */
function mmss(sec) {
  if (!isFinite(sec) || sec < 0) return '--:--';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
}

/**
 * Hauteurs de barres STABLES pour une URL donnée. Un simple aléatoire redessinerait
 * l'onde à chaque rendu (et différemment chez chaque participant), ce qui donnerait
 * l'impression d'un bug. On dérive donc les hauteurs de l'URL elle-même.
 */
function barresPour(url) {
  let h = 0;
  for (let i = 0; i < (url || '').length; i++) h = ((h << 5) - h + url.charCodeAt(i)) | 0;
  const out = [];
  for (let i = 0; i < NB_BARRES; i++) {
    h = (h * 1103515245 + 12345) & 0x7fffffff;
    out.push(0.28 + ((h >> 8) % 1000) / 1000 * 0.72); // entre 28 % et 100 %
  }
  return out;
}

const AudioMessage = memo(function AudioMessage({ src, compact }) {
  const audioRef = useRef(null);
  const [enLecture, setEnLecture] = useState(false);
  const [duree, setDuree] = useState(NaN);
  const [position, setPosition] = useState(0);
  const [vitesse, setVitesse] = useState(1);
  const [erreur, setErreur] = useState(false);

  const barres = useMemo(() => barresPour(src), [src]);

  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;
    const onMeta = () => setDuree(a.duration);
    const onTemps = () => setPosition(a.currentTime);
    const onFin = () => { setEnLecture(false); setPosition(0); };
    const onErr = () => setErreur(true);
    a.addEventListener('loadedmetadata', onMeta);
    a.addEventListener('timeupdate', onTemps);
    a.addEventListener('ended', onFin);
    a.addEventListener('error', onErr);
    return () => {
      a.removeEventListener('loadedmetadata', onMeta);
      a.removeEventListener('timeupdate', onTemps);
      a.removeEventListener('ended', onFin);
      a.removeEventListener('error', onErr);
    };
  }, [src]);

  const basculer = () => {
    const a = audioRef.current;
    if (!a) return;
    if (enLecture) { a.pause(); setEnLecture(false); return; }
    // La lecture peut être refusée (politique de lecture automatique, fichier
    // illisible) : on ne laisse pas l'interface prétendre qu'elle joue.
    const p = a.play();
    if (p && p.then) p.then(() => setEnLecture(true)).catch(() => setErreur(true));
    else setEnLecture(true);
  };

  const changerVitesse = () => {
    const suivante = VITESSES[(VITESSES.indexOf(vitesse) + 1) % VITESSES.length];
    setVitesse(suivante);
    if (audioRef.current) audioRef.current.playbackRate = suivante;
  };

  // Se déplacer dans le message en cliquant sur l'onde.
  const allerA = (e) => {
    const a = audioRef.current;
    if (!a || !isFinite(duree)) return;
    const r = e.currentTarget.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    a.currentTime = ratio * duree;
    setPosition(a.currentTime);
  };

  const avancement = isFinite(duree) && duree > 0 ? position / duree : 0;

  if (erreur) {
    return (
      <div style={{ fontSize: '12px', color: 'rgba(255,255,255,0.5)', padding: '8px 12px' }}>
        Message vocal illisible.
      </div>
    );
  }

  return (
    <div
      data-testid="lecteur-vocal"
      style={{
        display: 'flex', alignItems: 'center', gap: '10px',
        padding: '8px 12px', borderRadius: '18px',
        background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.10)',
        border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.28)',
        maxWidth: compact ? '260px' : '300px'
      }}
    >
      <audio ref={audioRef} src={src} preload="metadata" style={{ display: 'none' }} />

      {/* Bouton rond lecture / pause */}
      <button
        type="button"
        onClick={basculer}
        aria-label={enLecture ? 'Pause' : 'Lecture'}
        data-testid="vocal-lecture"
        style={{
          width: '34px', height: '34px', borderRadius: '50%', flexShrink: 0,
          background: PRIMAIRE, border: 'none', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0
        }}
      >
        {enLecture ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="#fff">
            <rect x="6" y="4" width="4" height="16" rx="1" />
            <rect x="14" y="4" width="4" height="16" rx="1" />
          </svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="#fff">
            <path d="M8 5v14l11-7z" />
          </svg>
        )}
      </button>

      {/* Onde : les barres déjà lues prennent la couleur du coach. */}
      <div
        onClick={allerA}
        style={{ flex: 1, display: 'flex', alignItems: 'center', gap: '2px',
                 height: '26px', cursor: 'pointer', minWidth: 0 }}
      >
        {barres.map((h, i) => {
          const lue = i / NB_BARRES <= avancement;
          return (
            <span
              key={i}
              style={{
                flex: 1, minWidth: '2px', height: Math.round(h * 22) + 'px',
                borderRadius: '2px',
                background: lue ? PRIMAIRE : 'rgba(var(--primary-rgb, 217, 28, 210), 0.28)',
                transition: 'background 0.1s linear'
              }}
            />
          );
        })}
      </div>

      {/* Temps écoulé pendant la lecture, durée totale au repos. */}
      <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.75)', flexShrink: 0,
                     fontVariantNumeric: 'tabular-nums' }}
            data-testid="vocal-duree">
        {mmss(enLecture || position > 0 ? position : duree)}
      </span>

      {/* Vitesse de lecture */}
      <button
        type="button"
        onClick={changerVitesse}
        title="Vitesse de lecture"
        data-testid="vocal-vitesse"
        style={{
          flexShrink: 0, minWidth: '30px', padding: '2px 5px', borderRadius: '9px',
          border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.45)',
          background: 'transparent', color: PRIMAIRE,
          fontSize: '10px', fontWeight: 700, cursor: 'pointer'
        }}
      >
        {vitesse}x
      </button>
    </div>
  );
});

export default AudioMessage;

/**
 * V610g — AfroboostAudioPlayer : LE lecteur audio d'Afroboost (plus de lecteur natif gris).
 *
 * Capsule fuchsia (couleur du coach), bouton rond Lecture / Pause, onde cliquable qui
 * sert de barre de progression, temps écoulé / durée, vitesse 1x -> 1.25x -> 1.5x -> 2x.
 * Lecture UNIQUEMENT au clic : `preload="none"`, jamais `autoplay`. Un même composant
 * pour l'éditeur coach, le message avant réservation et « Deviens Afroboosteur ».
 *
 * `testidAudio` / `testidBouton` : identifiants stables (bancs existants).
 * Libellés du bouton : « Écouter le message » -> « Pause » -> « Reprendre le message ».
 */
import React, { forwardRef, useImperativeHandle, useMemo, useRef, useState } from 'react';
import SvgIcon from './SvgIcon';

const PRIMAIRE = 'var(--primary-color, #D91CD2)';
const rgbaP = (a) => `rgba(var(--primary-rgb, 217, 28, 210), ${a})`;
export const VITESSES = [1, 1.25, 1.5, 2];
const BARRES = 36;

/** Une onde stable pour une adresse donnée (pas de décodage audio : léger et instantané). */
export function ondeDepuis(url, n = BARRES) {
  let h = 2166136261;
  for (const c of String(url || 'afroboost')) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619) >>> 0; }
  const sortie = [];
  for (let i = 0; i < n; i += 1) {
    h = Math.imul(h ^ (h >>> 13), 1274126177) >>> 0;
    const base = 0.35 + 0.65 * Math.abs(Math.sin((i / n) * Math.PI));   // enveloppe douce
    sortie.push(Math.max(0.18, Math.min(1, base * (0.45 + (h % 1000) / 1800))));
  }
  return sortie;
}

export function temps(s) {
  const t = Math.max(0, Math.floor(Number(s) || 0));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
}

/**
 * V610k — `ref.lire()` / `ref.pause()` : un parcours peut lancer le message PENDANT un geste
 * de l'utilisateur (seule façon d'avoir le son sur Safari). `lire()` rend la promesse de
 * play() : refusée -> le lecteur reste tel quel, « Écouter le message » (jamais bloquant).
 */
function AfroboostAudioPlayer({ src, titre = '', testidAudio, testidBouton, compact = false, inerte = false, preload = 'none' }, refExterne) {
  const ref = useRef(null);
  const [etat, setEtat] = useState('arret');     // 'arret' | 'lecture' | 'pause'
  const [pos, setPos] = useState(0);
  const [duree, setDuree] = useState(0);
  const [vitesse, setVitesse] = useState(1);
  const onde = useMemo(() => ondeDepuis(src), [src]);
  const avance = duree > 0 ? Math.min(1, pos / duree) : 0;

  const basculer = () => {
    const a = ref.current;
    if (!a || inerte) return;
    if (a.paused) {
      const p = a.play();
      if (p && typeof p.then === 'function') p.then(() => setEtat('lecture')).catch(() => setEtat('arret'));
      else setEtat('lecture');
    } else {
      a.pause();
      setEtat('pause');
    }
  };
  const chercher = (e) => {
    const a = ref.current;
    if (!a || !duree || inerte) return;
    const r = e.currentTarget.getBoundingClientRect();
    const f = Math.min(1, Math.max(0, (e.clientX - r.left) / (r.width || 1)));
    a.currentTime = f * duree;
    setPos(a.currentTime);
  };
  useImperativeHandle(refExterne, () => ({
    lire: () => {
      const a = ref.current;
      if (!a || inerte) return Promise.reject(new Error('indisponible'));
      const p = a.play();
      if (p && typeof p.then === 'function') return p.then(() => { setEtat('lecture'); }).catch((e) => { setEtat('arret'); throw e; });
      setEtat('lecture'); return Promise.resolve();
    },
    pause: () => { const a = ref.current; if (a && !a.paused) a.pause(); },
  }), [inerte]);

  const changerVitesse = () => {
    const i = (VITESSES.indexOf(vitesse) + 1) % VITESSES.length;
    setVitesse(VITESSES[i]);
    if (ref.current) ref.current.playbackRate = VITESSES[i];
  };
  const libelle = etat === 'lecture' ? 'Pause' : etat === 'pause' ? 'Reprendre le message' : 'Écouter le message';

  return (
    <div data-testid="afroboost-audio-player" style={{ display: 'flex', alignItems: 'center', gap: compact ? 10 : 12, padding: compact ? '8px 12px 8px 8px' : '10px 14px 10px 10px',
      borderRadius: 999, background: `linear-gradient(135deg, ${PRIMAIRE}, ${rgbaP(0.72)})`, boxShadow: `0 6px 22px ${rgbaP(0.35)}`,
      color: 'rgba(255,255,255,1)', minWidth: 0, maxWidth: '100%', boxSizing: 'border-box' }}>
      <button type="button" onClick={basculer} data-testid={testidBouton} aria-label={libelle} aria-pressed={etat === 'lecture'} title={libelle}
              style={{ flex: '0 0 auto', width: compact ? 38 : 44, height: compact ? 38 : 44, borderRadius: 999, border: 'none', cursor: inerte ? 'default' : 'pointer',
                background: 'rgba(255,255,255,0.98)', color: PRIMAIRE, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
        <SvgIcon name={etat === 'lecture' ? 'pause' : 'play'} size={compact ? 16 : 18} />
        <span style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>{libelle}</span>
      </button>
      <div style={{ flex: '1 1 auto', minWidth: 0 }}>
        {titre ? <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{titre}</div> : null}
        <div role="slider" tabIndex={0} aria-label="Position de lecture" aria-valuemin={0} aria-valuemax={Math.round(duree)} aria-valuenow={Math.round(pos)}
             onClick={chercher} data-testid="afroboost-audio-onde"
             style={{ display: 'flex', alignItems: 'center', gap: compact ? 1 : 2, height: compact ? 22 : 26, minWidth: 0, overflow: 'hidden', cursor: duree ? 'pointer' : 'default' }}>
          {onde.map((h, i) => (
            <span key={i} style={{ flex: '1 1 0', minWidth: 1, height: `${Math.round(h * 100)}%`, borderRadius: 2,
              background: (i + 0.5) / onde.length <= avance ? 'rgba(255,255,255,1)' : 'rgba(255,255,255,0.42)' }} />
          ))}
        </div>
      </div>
      <span data-testid="afroboost-audio-temps" style={{ flex: '0 0 auto', fontSize: compact ? 11 : 12, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums', opacity: 0.95 }}>
        {etat === 'arret' && !pos ? temps(duree) : `${temps(pos)} / ${temps(duree)}`}
      </span>
      <button type="button" onClick={changerVitesse} data-testid="afroboost-audio-vitesse" aria-label="Vitesse de lecture"
              style={{ flex: '0 0 auto', minWidth: 40, height: 28, borderRadius: 999, border: '1px solid rgba(255,255,255,0.55)', background: 'rgba(255,255,255,0.14)',
                color: 'rgba(255,255,255,1)', fontSize: 12, fontWeight: 800, cursor: 'pointer' }}>
        {`${vitesse}x`}
      </button>
      <audio ref={ref} src={src} preload={preload} data-testid={testidAudio}
             onLoadedMetadata={(e) => setDuree(e.currentTarget.duration || 0)} onDurationChange={(e) => setDuree(e.currentTarget.duration || 0)}
             onTimeUpdate={(e) => setPos(e.currentTarget.currentTime || 0)}
             onEnded={() => { setEtat('arret'); setPos(0); }}
             onPause={() => setEtat((x) => (x === 'lecture' ? 'pause' : x))} />
    </div>
  );
}

export default forwardRef(AfroboostAudioPlayer);

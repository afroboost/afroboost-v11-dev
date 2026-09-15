/**
 * DÉCOUPE VIDÉO — non destructive.
 *
 * L'original n'est jamais réencodé ni écrasé : l'offre stocke un point
 * d'entrée et un point de sortie en secondes (`video_trim_start`,
 * `video_trim_end`), et CHAQUE lecteur (preview admin, carte, fiche, plein
 * écran — c'est le même élément <video>) joue uniquement cette séquence.
 *
 * Ici : les règles pures (validation, formatage) et le hook React qui borne
 * la lecture d'un <video>. Une seule implémentation, consommée partout.
 */
import { useEffect } from 'react';

const DUREE_MIN_S = 0.5;

const nombre = (v) => {
  const n = typeof v === 'string' ? parseFloat(v) : v;
  return Number.isFinite(n) && n >= 0 ? n : null;
};

/**
 * { start, end } valides — ou null si la découpe est absente / incohérente
 * (fin ≤ début, extrait < 0,5 s). `duree` (optionnelle) borne la fin.
 */
export const trimValide = (start, end, duree) => {
  let s = nombre(start);
  let e = nombre(end);
  if (s == null && e == null) return null;
  if (s == null) s = 0;
  const d = nombre(duree);
  if (e == null || (d != null && e > d)) e = d != null ? d : e;
  if (e == null) return null;
  if (d != null && s >= d) return null;
  if (e - s < DUREE_MIN_S) return null;
  return { start: Math.round(s * 100) / 100, end: Math.round(e * 100) / 100 };
};

/** La découpe portée par une offre, ou null. */
export const trimDeLOffre = (offre) => trimValide(offre && offre.video_trim_start, offre && offre.video_trim_end);

/** « 00:15 » (mm:ss), ou « 1:02:03 » au-delà d'une heure. */
export const formatTemps = (secondes) => {
  const t = Math.max(0, Math.round(nombre(secondes) || 0));
  const h = Math.floor(t / 3600); const m = Math.floor((t % 3600) / 60); const s = t % 60;
  const mm = String(m).padStart(2, '0'); const ss = String(s).padStart(2, '0');
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
};

/** Le résumé affiché au coach : durée totale, début, fin, extrait gardé. */
export const resumeTrim = (duree, trim) => {
  const d = nombre(duree) || 0;
  const t = trim || { start: 0, end: d };
  return {
    total: formatTemps(d),
    debut: formatTemps(t.start),
    fin: formatTemps(t.end),
    extrait: formatTemps(Math.max(0, t.end - t.start)),
    secondes: Math.max(0, t.end - t.start),
  };
};

/**
 * Borne la lecture d'un <video> à [start, end].
 *  - au chargement des métadonnées : positionne sur `start` ;
 *  - à chaque `timeupdate` : au-delà de `end`, reboucle sur `start` (loop)
 *    ou met en pause et revient au début de l'extrait ;
 *  - à `play` : si la tête est hors de l'extrait, repart de `start`.
 * Sans découpe, ne pose aucun écouteur : le lecteur reste natif.
 * `ref` = React ref de l'élément vidéo ; `trim` = { start, end } ou null.
 */
export function useTrimVideo(ref, trim, options = {}) {
  const start = trim ? trim.start : null;
  const end = trim ? trim.end : null;
  const loop = !!options.loop;
  useEffect(() => {
    const v = ref && ref.current;
    if (!v || start == null || end == null) return undefined;
    const horsExtrait = () => v.currentTime < start - 0.05 || v.currentTime >= end;
    const auDebut = () => { try { v.currentTime = start; } catch (e) { /* metadonnees absentes */ } };
    const onMeta = () => { auDebut(); };
    const onTime = () => {
      if (v.currentTime >= end) {
        if (loop) { auDebut(); const p = v.play(); if (p && p.catch) p.catch(() => {}); }
        else { v.pause(); auDebut(); }
      } else if (v.currentTime < start - 0.05) {
        auDebut();
      }
    };
    const onPlay = () => { if (horsExtrait()) auDebut(); };
    v.addEventListener('loadedmetadata', onMeta);
    v.addEventListener('timeupdate', onTime);
    v.addEventListener('play', onPlay);
    if (v.readyState >= 1) auDebut();
    return () => {
      v.removeEventListener('loadedmetadata', onMeta);
      v.removeEventListener('timeupdate', onTime);
      v.removeEventListener('play', onPlay);
    };
  }, [ref, start, end, loop]);
}

/**
 * VideoTrimEditor — L'UNIQUE éditeur vidéo d'Afroboost.
 *
 * Utilisé par « Modifier l'offre > Médias » (OfferWizard) ET par « Nouvelle
 * publication » (PublishModal). Un seul composant, une seule logique : un
 * correctif ici profite aux deux.
 *
 * Ce qu'il fait, et rien de plus (pas de montage, pas d'effets) :
 *  - APERÇU : le lecteur au vrai ratio du média (lisible), sans contrôles natifs ;
 *  - DÉCOUPE non destructive : deux poignées (début / fin) sur une timeline, la
 *    zone conservée est surlignée ; résumé « vidéo originale / début / fin /
 *    durée finale » ; « Réinitialiser » ;
 *  - LECTURE DE L'EXTRAIT : ▶ Lire l'extrait (se place à `start`, s'arrête
 *    exactement à `end`, revient au début de l'extrait), ⏸ Pause, ↺ Rejouer ;
 *    un curseur de lecture (scrub) borné à l'extrait, au dixième de seconde ;
 *  - MINIATURE : « Capturer cette image comme miniature » = la frame affichée,
 *    forcément DANS l'extrait ; attend qu'une vraie frame soit décodée (V419,
 *    jamais une image noire) ; aperçu « Miniature sélectionnée », re-capture.
 *
 * L'original n'est jamais réencodé : le parent reçoit `onTrimChange({start,end})`
 * (ou null) et `onThumbnailCapture(blob, objectUrl)`. La lecture bornée passe
 * par `useTrimVideo` (utils/videoTrim.js), le MÊME hook que la vitrine.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import SvgIcon from './SvgIcon';
import { stylesLecteur, normaliserRatio } from '../utils/videoRatio';
import { trimValide, resumeTrim, formatTemps, useTrimVideo } from '../utils/videoTrim';

const COULEUR = 'var(--primary-color, #D91CD2)';
const RGB = 'var(--primary-rgb, 217, 28, 210)';
const EXTRAIT_MIN_S = 0.5;

/** V419 — attendre qu'une frame soit RÉELLEMENT décodée avant de la peindre. */
export const attendreFrame = (v) => new Promise((res) => {
  let fini = false;
  const finir = () => { if (!fini) { fini = true; res(); } };
  const secours = setTimeout(finir, 1200);
  const terminer = () => { clearTimeout(secours); finir(); };
  if (typeof v.requestVideoFrameCallback === 'function') { v.requestVideoFrameCallback(() => terminer()); return; }
  const verifier = () => {
    if (fini) return;
    if (v.readyState >= 2) requestAnimationFrame(() => requestAnimationFrame(terminer));
    else setTimeout(verifier, 60);
  };
  verifier();
});

/** La frame courante d'un <video>, en blob JPEG (null si rien à peindre). */
export const capturerFrame = (v) => new Promise((res) => {
  if (!v || !v.videoWidth || !v.videoHeight) { res(null); return; }
  try {
    const canvas = document.createElement('canvas');
    canvas.width = v.videoWidth; canvas.height = v.videoHeight;
    canvas.getContext('2d').drawImage(v, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((b) => res(b || null), 'image/jpeg', 0.9);
  } catch (e) { res(null); }   // vidéo d'une autre origine sans CORS : toile « salie »
});

const estAutreOrigine = (url) => {
  try { return /^https?:\/\//i.test(url) && new URL(url).origin !== window.location.origin; } catch (e) { return false; }
};

export default function VideoTrimEditor({
  videoUrl, trimStart, trimEnd, aspectRatio, thumbnail,
  onTrimChange, onThumbnailCapture, onMetadata, onAutoCapture,
  hauteurMax = '320px', posterUrl = '', libelleCapture = 'Capturer cette image comme miniature',
  disposition = 'colonne', complement = null, sousApercu = null,
}) {
  // Capture AUTOMATIQUE (une fois par vidéo) : une miniature par défaut, prise
  // à ~1 s (la frame 0 est souvent noire) une fois une vraie frame décodée.
  const autoFaitRef = useRef('');
  const videoRef = useRef(null);
  const [duree, setDuree] = useState(0);
  const [position, setPosition] = useState(0);
  const [enLecture, setEnLecture] = useState(false);
  const [erreur, setErreur] = useState('');
  const [captureEnCours, setCaptureEnCours] = useState(false);
  // SON : coupé tant que l'utilisateur n'a rien demandé (règles navigateur) ;
  // « Lire l'extrait » est un geste utilisateur → la lecture part AVEC le son,
  // sauf si le coach l'a coupé lui-même (🔇).
  const [son, setSon] = useState(true);

  const trim = useMemo(() => trimValide(trimStart, trimEnd, duree || undefined), [trimStart, trimEnd, duree]);
  const debut = trim ? trim.start : 0;
  const fin = trim ? trim.end : duree;
  const r = resumeTrim(duree, trim);
  const ratio = normaliserRatio(aspectRatio);
  const st = stylesLecteur(ratio, { hauteurMax });

  // Lecture bornée : après `fin`, pause + retour au début de l'extrait.
  useTrimVideo(videoRef, trim, { loop: false });

  // Le lecteur suit sa position (scrub + affichage) et son état.
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return undefined;
    const onTime = () => setPosition(v.currentTime);
    const onPlay = () => setEnLecture(true);
    const onPause = () => setEnLecture(false);
    v.addEventListener('timeupdate', onTime);
    v.addEventListener('seeked', onTime);
    v.addEventListener('play', onPlay);
    v.addEventListener('pause', onPause);
    v.addEventListener('ended', onPause);
    return () => {
      v.removeEventListener('timeupdate', onTime); v.removeEventListener('seeked', onTime);
      v.removeEventListener('play', onPlay); v.removeEventListener('pause', onPause); v.removeEventListener('ended', onPause);
    };
  }, [videoUrl]);

  // Nouvelle vidéo : on repart de zéro (durée inconnue, pas d'erreur).
  useEffect(() => { setDuree(0); setPosition(0); setErreur(''); setEnLecture(false); }, [videoUrl]);

  const aller = (t) => {
    const v = videoRef.current;
    if (!v) return;
    try { v.currentTime = Math.max(debut, Math.min(fin || t, t)); } catch (e) { /* métadonnées absentes */ }
    setPosition(v.currentTime);
  };
  const lire = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.currentTime < debut - 0.05 || v.currentTime >= fin) aller(debut);
    v.muted = !son;
    const p = v.play();
    if (p && p.catch) {
      p.catch(() => {
        // Le navigateur refuse l'audio : on relance en muet plutôt qu'une vidéo figée.
        v.muted = true; setSon(false);
        const q = v.play(); if (q && q.catch) q.catch(() => {});
      });
    }
  };
  const basculerSon = () => {
    const v = videoRef.current;
    const suivant = !son;
    setSon(suivant);
    if (v) v.muted = !suivant;
  };
  const pause = () => { const v = videoRef.current; if (v) v.pause(); };
  const rejouer = () => { aller(debut); lire(); };

  const poserTrim = (s, e) => {
    if (!onTrimChange) return;
    const d = duree || 0;
    const ns = Math.max(0, Math.min(s, d)); const ne = Math.max(0, Math.min(e, d));
    if (ne - ns < EXTRAIT_MIN_S) return;               // extrait trop court : on ignore
    onTrimChange({ start: Math.round(ns * 100) / 100, end: Math.round(ne * 100) / 100 });
    // La preview utilise immédiatement les nouvelles bornes.
    const v = videoRef.current;
    if (v && (v.currentTime < ns || v.currentTime > ne)) { try { v.currentTime = ns; } catch (err) { /* ignore */ } }
  };
  const reinitialiser = () => { if (onTrimChange) onTrimChange(null); };

  const capturer = async () => {
    const v = videoRef.current;
    if (!v || !onThumbnailCapture) return;
    setErreur(''); setCaptureEnCours(true);
    try {
      // Jamais une frame hors de l'extrait : on rentre dedans d'abord.
      if (trim && (v.currentTime < debut - 0.05 || v.currentTime > fin)) {
        v.currentTime = debut;
        await new Promise((res) => { const fin2 = () => { v.removeEventListener('seeked', fin2); res(); }; v.addEventListener('seeked', fin2); setTimeout(res, 800); });
      }
      await attendreFrame(v);
      const blob = await capturerFrame(v);
      if (!blob) { setErreur('Capture impossible sur cette vidéo (hébergement externe sans autorisation).'); return; }
      onThumbnailCapture(blob, URL.createObjectURL(blob), v.currentTime);
    } finally { setCaptureEnCours(false); }
  };

  const pct = (t) => (duree > 0 ? Math.max(0, Math.min(100, (t / duree) * 100)) : 0);
  const pas = duree > 60 ? 0.5 : 0.1;

  // DISPOSITION : « colonne » (mobile / étroit) empile tout ; « colonnes »
  // (desktop) met la grande vidéo à gauche et la découpe, la miniature et le
  // `complement` du parent (légende, actions…) à droite — moins de défilement.
  const colonnes = disposition === 'colonnes';
  const styleRacine = colonnes
    ? { display: 'grid', gridTemplateColumns: 'minmax(0, 1.2fr) minmax(0, 1fr)', gap: 20, alignItems: 'start' }
    : { display: 'grid', gap: 10 };
  return (
    <div data-testid="video-trim-editor" data-disposition={disposition} style={styleRacine}>
      <div style={{ display: 'grid', gap: 10, minWidth: 0 }} data-testid="vte-zone-video">
      <style>{`
        .vte-range{-webkit-appearance:none;appearance:none;width:100%;height:4px;background:rgba(255,255,255,0.18);border-radius:2px;outline:none;margin:0}
        .vte-range::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:16px;height:16px;border-radius:50%;background:var(--primary-color,#D91CD2);border:2px solid #fff;cursor:pointer}
        .vte-range::-moz-range-thumb{width:16px;height:16px;border-radius:50%;background:var(--primary-color,#D91CD2);border:2px solid #fff;cursor:pointer}
        .vte-poignee{-webkit-appearance:none;appearance:none;position:absolute;left:0;top:0;width:100%;height:22px;background:transparent;margin:0;pointer-events:none;outline:none}
        .vte-poignee::-webkit-slider-runnable-track{background:transparent;height:22px}
        .vte-poignee::-moz-range-track{background:transparent;height:22px}
        .vte-poignee::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;pointer-events:auto;width:14px;height:22px;border-radius:5px;background:var(--primary-color,#D91CD2);border:2px solid #fff;cursor:ew-resize;margin-top:0}
        .vte-poignee::-moz-range-thumb{pointer-events:auto;width:14px;height:22px;border-radius:5px;background:var(--primary-color,#D91CD2);border:2px solid #fff;cursor:ew-resize}
      `}</style>

      {/* APERÇU — le vrai ratio du média, lisible. Pas de contrôles natifs : les
          nôtres sont bornés à l'extrait. */}
      <div style={{ ...st.conteneur, minHeight: 160, borderRadius: 10 }} data-testid="vte-apercu" data-ratio={ratio}>
        <video
          ref={videoRef}
          key={videoUrl}
          src={videoUrl}
          poster={posterUrl || undefined}
          playsInline
          muted={!son || !enLecture}
          preload="auto"
          crossOrigin={estAutreOrigine(videoUrl) ? 'anonymous' : undefined}
          style={st.video}
          onLoadedMetadata={(e) => {
            const v = e.currentTarget;
            const d = Number.isFinite(v.duration) ? Math.round(v.duration * 100) / 100 : 0;
            setDuree(d);
            if (onMetadata) onMetadata({ duration: d, width: v.videoWidth, height: v.videoHeight });
            // Se placer au début de l'extrait (ou à 1 s : la frame 0 est souvent noire).
            const t = trim ? trim.start : Math.min(1, Math.max(0.1, d * 0.25));
            try { v.currentTime = t; } catch (err) { /* ignore */ }
            if (onAutoCapture && autoFaitRef.current !== videoUrl) {
              autoFaitRef.current = videoUrl;
              const apresSeek = async () => {
                v.removeEventListener('seeked', apresSeek);
                await attendreFrame(v);
                const blob = await capturerFrame(v);
                if (blob) onAutoCapture(blob, URL.createObjectURL(blob), v.currentTime);
              };
              v.addEventListener('seeked', apresSeek);
              setTimeout(() => { v.removeEventListener('seeked', apresSeek); }, 3000);
            }
          }}
          onError={() => setErreur('Vidéo illisible (fichier ou lien invalide).')}
        />
      </div>

      {/* CONTRÔLES DE L'EXTRAIT */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        {!enLecture ? (
          <button type="button" onClick={lire} data-testid="vte-lire" disabled={!duree}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 12px', borderRadius: 999, border: 'none', background: COULEUR, color: '#fff', fontSize: 12, fontWeight: 700, cursor: duree ? 'pointer' : 'default', opacity: duree ? 1 : 0.5 }}>
            <SvgIcon name="play" size={14} /> Lire l'extrait
          </button>
        ) : (
          <button type="button" onClick={pause} data-testid="vte-pause"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 12px', borderRadius: 999, border: `1px solid ${COULEUR}`, background: 'transparent', color: COULEUR, fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>
            <SvgIcon name="stop" size={14} /> Pause
          </button>
        )}
        <button type="button" onClick={rejouer} data-testid="vte-rejouer" disabled={!duree}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 12px', borderRadius: 999, border: '1px solid rgba(255,255,255,0.2)', background: 'transparent', color: 'rgba(255,255,255,0.85)', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
          <SvgIcon name="refresh" size={14} /> Rejouer
        </button>
        <button type="button" onClick={basculerSon} data-testid="vte-son" aria-pressed={son} aria-label={son ? 'Couper le son' : 'Activer le son'} title={son ? 'Son activé' : 'Son coupé'}
          style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, borderRadius: 16, border: `1px solid ${son ? COULEUR : 'rgba(255,255,255,0.2)'}`, background: son ? `rgba(${RGB}, 0.15)` : 'transparent', color: son ? COULEUR : 'rgba(255,255,255,0.6)', cursor: 'pointer' }}>
          <SvgIcon name={son ? 'volume2' : 'volumeX'} size={14} />
        </button>
        <span style={{ marginLeft: 'auto', fontSize: 12, color: 'rgba(255,255,255,0.7)', fontVariantNumeric: 'tabular-nums' }} data-testid="vte-position">
          {formatTemps(position)} / {formatTemps(duree)}
        </span>
      </div>

      {/* SCRUB — borné à l'extrait, au dixième de seconde. */}
      <div>
        <input className="vte-range" type="range" min={debut} max={fin || 0} step={0.1} value={Math.min(Math.max(position, debut), fin || 0)}
          onChange={(e) => aller(parseFloat(e.target.value))} aria-label="Position dans l'extrait" data-testid="vte-scrub" disabled={!duree} />
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'rgba(255,255,255,0.45)', marginTop: 2 }}>
          <span>{formatTemps(debut)}</span><span>{formatTemps(fin)}</span>
        </div>
      </div>

      {sousApercu}
      </div>
      <div style={{ display: 'grid', gap: 10, minWidth: 0 }} data-testid="vte-zone-reglages">
      {/* DÉCOUPE — deux poignées sur une même piste, zone conservée surlignée. */}
      <div style={{ padding: '10px 10px 8px', background: 'rgba(255,255,255,0.05)', borderRadius: 10 }} data-testid="vte-decoupe">
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 700, color: '#fff', marginBottom: 6 }}>
          <span style={{ color: COULEUR, display: 'inline-flex' }}><SvgIcon name="edit" size={14} /></span> Découper la vidéo
        </div>
        {!duree ? (
          <p style={{ margin: 0, fontSize: 11, color: 'rgba(255,255,255,0.5)' }} data-testid="vte-attente">Chargement de la vidéo… la découpe apparaît dès que sa durée est connue.</p>
        ) : (
          <>
            <div style={{ position: 'relative', height: 22 }} data-testid="vte-timeline">
              {/* Parties SUPPRIMÉES (assombries) | zone CONSERVÉE (couleur de marque) | supprimées */}
              <div style={{ position: 'absolute', left: 0, right: 0, top: 6, height: 10, borderRadius: 5, background: 'rgba(0,0,0,0.45)', border: '1px solid rgba(255,255,255,0.12)' }} />
              <div data-testid="vte-exclu-avant" style={{ position: 'absolute', top: 6, height: 10, left: 0, width: `${pct(debut)}%`, background: 'repeating-linear-gradient(135deg, rgba(255,255,255,0.08) 0 4px, transparent 4px 8px)', borderRadius: '5px 0 0 5px' }} />
              <div data-testid="vte-exclu-apres" style={{ position: 'absolute', top: 6, height: 10, left: `${pct(fin)}%`, right: 0, background: 'repeating-linear-gradient(135deg, rgba(255,255,255,0.08) 0 4px, transparent 4px 8px)', borderRadius: '0 5px 5px 0' }} />
              <div data-testid="vte-zone" style={{ position: 'absolute', top: 6, height: 10, borderRadius: 3, background: `linear-gradient(90deg, ${COULEUR}, rgba(139, 92, 246, 0.9))`, left: `${pct(debut)}%`, width: `${Math.max(0, pct(fin) - pct(debut))}%`, boxShadow: `0 0 10px rgba(${RGB}, 0.6)` }} />
              <input className="vte-poignee" type="range" min={0} max={duree} step={pas} value={debut} aria-label="Début de l'extrait" data-testid="vte-start"
                onChange={(e) => poserTrim(parseFloat(e.target.value), fin)} />
              <input className="vte-poignee" type="range" min={0} max={duree} step={pas} value={fin} aria-label="Fin de l'extrait" data-testid="vte-end"
                onChange={(e) => poserTrim(debut, parseFloat(e.target.value))} />
            </div>
            {/* Réglage FIN au dixième de seconde : [-] 00:05.0 [+] */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8, marginTop: 8 }} data-testid="vte-fin-reglage">
              {[{ cle: 'debut', libelle: 'Début', val: debut, poser: (t) => poserTrim(t, fin) }, { cle: 'fin', libelle: 'Fin', val: fin, poser: (t) => poserTrim(debut, t) }].map((c) => (
                <div key={c.cle} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(0,0,0,0.25)', borderRadius: 8, padding: '4px 6px' }}>
                  <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.6)', minWidth: 36 }}>{c.libelle}</span>
                  <button type="button" data-testid={`vte-${c.cle}-moins`} onClick={() => c.poser(Math.round((c.val - 0.1) * 10) / 10)} aria-label={`${c.libelle} : reculer de 0,1 s`}
                    style={{ width: 28, height: 28, borderRadius: 14, border: '1px solid rgba(255,255,255,0.2)', background: 'transparent', color: '#fff', cursor: 'pointer', fontWeight: 700 }}>−</button>
                  <span data-testid={`vte-${c.cle}-precis`} style={{ flex: 1, textAlign: 'center', fontSize: 13, fontWeight: 700, color: '#fff', fontVariantNumeric: 'tabular-nums' }}>{formatTemps(c.val)}.{Math.round((c.val % 1) * 10) % 10}</span>
                  <button type="button" data-testid={`vte-${c.cle}-plus`} onClick={() => c.poser(Math.round((c.val + 0.1) * 10) / 10)} aria-label={`${c.libelle} : avancer de 0,1 s`}
                    style={{ width: 28, height: 28, borderRadius: 14, border: '1px solid rgba(255,255,255,0.2)', background: 'transparent', color: '#fff', cursor: 'pointer', fontWeight: 700 }}>+</button>
                </div>
              ))}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '2px 12px', fontSize: 12, color: 'rgba(255,255,255,0.85)', marginTop: 8 }} data-testid="vte-resume">
              <span>Vidéo originale : <b data-testid="vte-total">{r.total}</b></span>
              <span>Extrait final : <b data-testid="vte-extrait">{r.extrait}</b></span>
              <span>Début : <b data-testid="vte-debut">{r.debut}</b></span>
              <span>Fin : <b data-testid="vte-fin">{r.fin}</b></span>
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <button type="button" onClick={reinitialiser} data-testid="vte-reset" disabled={!trim}
                style={{ fontSize: 11, padding: '5px 10px', borderRadius: 999, border: '1px solid rgba(255,255,255,0.2)', background: 'transparent', color: trim ? 'rgba(255,255,255,0.85)' : 'rgba(255,255,255,0.35)', cursor: trim ? 'pointer' : 'default' }}>
                Réinitialiser
              </button>
              <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)' }}>
                {trim ? `Seul l'extrait ${r.debut} → ${r.fin} sera joué. L'original n'est pas modifié.` : 'Déplace les poignées pour garder seulement la partie voulue.'}
              </span>
            </div>
          </>
        )}
      </div>

      {/* MINIATURE — la frame affichée, dans l'extrait. */}
      {onThumbnailCapture ? (
        <div data-testid="vte-miniature">
          <button type="button" onClick={capturer} disabled={!duree || captureEnCours} data-testid="vte-capturer"
            style={{ width: '100%', padding: '9px', borderRadius: 8, border: 'none', background: COULEUR, color: '#fff', fontSize: 13, fontWeight: 600, cursor: duree ? 'pointer' : 'default', opacity: duree && !captureEnCours ? 1 : 0.6 }}>
            {thumbnail ? 'Capturer une autre image' : libelleCapture}
          </button>
          {thumbnail ? (
            <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 10 }}>
              <img src={thumbnail} alt="Miniature sélectionnée" data-testid="vte-miniature-apercu"
                style={{ width: 96, height: 96, objectFit: 'cover', borderRadius: 8, border: `2px solid ${COULEUR}` }} />
              <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>Miniature sélectionnée</span>
            </div>
          ) : null}
        </div>
      ) : null}
      {erreur ? <p style={{ margin: 0, fontSize: 11, color: 'var(--danger-color, #f87171)' }} data-testid="vte-erreur">{erreur}</p> : null}
      {complement}
      </div>
    </div>
  );
}

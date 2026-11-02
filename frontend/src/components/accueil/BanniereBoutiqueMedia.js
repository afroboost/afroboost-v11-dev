import React, { useRef, useEffect } from 'react';

/**
 * V645.3c — MÉDIA DE LA BANNIÈRE BOUTIQUE (accueil).
 *
 * Vidéo : LECTURE DU SEGMENT [trim_start, trim_end] en boucle, muette, avec la
 * miniature en poster. Ce n'est PAS un recodage du fichier — on BORNE la lecture
 * (on revient à trim_start quand on atteint trim_end). Si aucun extrait valide
 * n'est configuré (trim_end <= trim_start), on lit le fichier ENTIER en boucle
 * native : une bannière vidéo d'avant ce lot rend donc exactement comme avant.
 * Image : simple <img>. Aucun média : fond dégradé discret (fallback).
 *
 * Indépendant des médias de l'offre T-shirt (lit uniquement les champs concept).
 */
export default function BanniereBoutiqueMedia({ url, type, trimStart, trimEnd, thumbnail }) {
  const videoRef = useRef(null);
  const ts = Number(trimStart || 0);
  const te = Number(trimEnd || 0);
  const decoupe = te > ts; // extrait valide ?

  useEffect(() => {
    const v = videoRef.current;
    if (!v || type !== 'video' || !decoupe) return undefined;
    const caler = () => {
      try { if (v.currentTime < ts || v.currentTime >= te) v.currentTime = ts; } catch (e) { /* ignore */ }
    };
    const surTemps = () => {
      if (v.currentTime >= te || v.currentTime < ts) {
        try {
          v.currentTime = ts;
          const p = v.play();
          if (p && typeof p.catch === 'function') p.catch(() => {});
        } catch (e) { /* ignore */ }
      }
    };
    v.addEventListener('loadedmetadata', caler);
    v.addEventListener('timeupdate', surTemps);
    if (v.readyState >= 1) caler();
    return () => {
      v.removeEventListener('loadedmetadata', caler);
      v.removeEventListener('timeupdate', surTemps);
    };
  }, [type, decoupe, ts, te, url]);

  if (!url) {
    return (
      <div
        className="af-boutique-banniere-media"
        style={{ background: 'linear-gradient(135deg, #0a0a0a 0%, rgba(var(--primary-rgb,217,28,210),0.18) 60%, rgba(var(--primary-rgb,217,28,210),0.08) 100%)' }}
      />
    );
  }
  if (type === 'video') {
    return (
      <video
        ref={videoRef}
        className="af-boutique-banniere-media"
        src={url}
        poster={thumbnail || undefined}
        autoPlay
        loop={!decoupe}
        muted
        playsInline
        preload="metadata"
      />
    );
  }
  return <img className="af-boutique-banniere-media" src={url} alt="Boutique Afroboost" loading="lazy" />;
}

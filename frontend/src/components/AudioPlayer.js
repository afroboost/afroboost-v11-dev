/**
 * AudioPlayer Component v35
 * Lecteur audio premium style Spotify + Glassmorphism
 * - Large thumbnail avec glow neon (pochette)
 * - Barre de progression fluide
 * - Mode preview 30s avec message explicite
 * - Bouton achat intégré après blocage
 * - Bouton Télécharger pour audios gratuits
 * - Description affichée
 * - Continue quand on change d'onglet (pas de pause auto)
 */
import React, { useState, useRef, useEffect, useCallback } from 'react';

const AudioPlayer = ({
  audioUrl,
  previewUrl,
  title = 'Audio',
  thumbnail,
  duration: durationProp,
  price,
  description,
  accentColor = '#D91CD2',
  isPreview = false,
  previewDuration = 30,
  onBuyClick
}) => {
  const audioRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(durationProp || 0);
  const [previewEnded, setPreviewEnded] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const src = isPreview ? (previewUrl || audioUrl) : audioUrl;
  const maxPreviewTime = previewDuration || 30;
  const isFree = !price || price <= 0;

  const formatTime = (s) => {
    if (!s || isNaN(s)) return '0:00';
    const min = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${min}:${sec.toString().padStart(2, '0')}`;
  };

  const togglePlay = useCallback(() => {
    if (!audioRef.current) return;
    if (previewEnded && isPreview) {
      // Reset to beginning for re-preview
      audioRef.current.currentTime = 0;
      setPreviewEnded(false);
      setCurrentTime(0);
      audioRef.current.play().catch(() => {});
      setIsPlaying(true);
      return;
    }
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play().catch(() => {});
      setIsPlaying(true);
      setPreviewEnded(false);
    }
  }, [isPlaying, previewEnded, isPreview]);

  const handleTimeUpdate = () => {
    if (!audioRef.current) return;
    setCurrentTime(audioRef.current.currentTime);

    if (isPreview && audioRef.current.currentTime >= maxPreviewTime) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      setIsPlaying(false);
      setPreviewEnded(true);
    }
  };

  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(isPreview ? Math.min(maxPreviewTime, audioRef.current.duration) : audioRef.current.duration);
    }
  };

  const handleSeek = (e) => {
    if (!audioRef.current || previewEnded) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const pct = x / rect.width;
    const maxTime = isPreview ? maxPreviewTime : duration;
    audioRef.current.currentTime = pct * maxTime;
  };

  const handleEnded = () => {
    setIsPlaying(false);
    setCurrentTime(0);
  };

  const handleDownload = () => {
    if (!audioUrl || !isFree) return;
    const url = audioUrl.startsWith('/api/') ? audioUrl : audioUrl;
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title}.mp3`;
    a.target = '_blank';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
      }
    };
  }, []);

  const progress = duration > 0 ? (currentTime / (isPreview ? Math.min(maxPreviewTime, duration) : duration)) * 100 : 0;

  return (
    <div
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '16px',
        padding: '16px',
        borderRadius: '18px',
        background: previewEnded ? 'rgba(217,28,210,0.06)' : 'rgba(10,5,20,0.6)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        border: `1px solid ${previewEnded ? 'rgba(217,28,210,0.3)' : isHovered ? `${accentColor}50` : 'rgba(255,255,255,0.06)'}`,
        position: 'relative',
        overflow: 'hidden',
        transition: 'all 0.3s ease',
        boxShadow: isHovered ? `0 0 30px ${accentColor}20` : 'none'
      }}
    >
      {/* Glow effect */}
      <div style={{
        position: 'absolute',
        top: '-30px',
        left: '-30px',
        width: '120px',
        height: '120px',
        borderRadius: '50%',
        background: `radial-gradient(circle, ${accentColor}15, transparent)`,
        filter: 'blur(25px)',
        pointerEvents: 'none'
      }} />

      <audio
        ref={audioRef}
        src={src}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onEnded={handleEnded}
        preload="metadata"
      />

      {/* Large Thumbnail / Pochette */}
      <div style={{ position: 'relative', flexShrink: 0 }}>
        <div style={{
          width: '80px',
          height: '80px',
          borderRadius: '14px',
          background: thumbnail ? 'none' : `linear-gradient(135deg, ${accentColor}40, ${accentColor}10)`,
          border: `2px solid ${previewEnded ? 'rgba(217,28,210,0.6)' : `${accentColor}60`}`,
          overflow: 'hidden',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: `0 0 25px ${accentColor}30, inset 0 0 20px ${accentColor}10`,
          cursor: 'pointer',
          position: 'relative'
        }}
          onClick={togglePlay}
        >
          {thumbnail ? (
            <img src={thumbnail} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          ) : (
            <span style={{ fontSize: '32px', filter: `drop-shadow(0 0 8px ${accentColor})` }}>🎵</span>
          )}
          {/* Play overlay */}
          <div style={{
            position: 'absolute',
            inset: 0,
            background: previewEnded ? 'rgba(0,0,0,0.7)' : 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexDirection: 'column',
            opacity: isHovered || previewEnded ? 1 : 0,
            transition: 'opacity 0.2s',
            borderRadius: '12px'
          }}>
            {previewEnded ? (
              <span style={{ fontSize: '11px', color: '#fff', fontWeight: 600 }}>🔒</span>
            ) : isPlaying ? (
              <svg width="24" height="24" fill="#fff" viewBox="0 0 24 24">
                <rect x="6" y="4" width="4" height="16" rx="1" />
                <rect x="14" y="4" width="4" height="16" rx="1" />
              </svg>
            ) : (
              <svg width="24" height="24" fill="#fff" viewBox="0 0 24 24">
                <polygon points="8 4 20 12 8 20 8 4" />
              </svg>
            )}
          </div>
        </div>
        {/* Preview badge */}
        {isPreview && (
          <span style={{
            position: 'absolute',
            top: '-5px',
            right: '-5px',
            fontSize: '10px',
            padding: '2px 7px',
            borderRadius: '6px',
            background: `linear-gradient(135deg, ${accentColor}, #8b5cf6)`,
            color: '#fff',
            fontWeight: 700,
            boxShadow: `0 0 10px ${accentColor}50`
          }}>
            {maxPreviewTime}s
          </span>
        )}
        {/* Price badge */}
        {price > 0 && (
          <span style={{
            position: 'absolute',
            bottom: '-5px',
            left: '50%',
            transform: 'translateX(-50%)',
            fontSize: '10px',
            padding: '2px 8px',
            borderRadius: '6px',
            background: 'rgba(34,197,94,0.9)',
            color: '#fff',
            fontWeight: 700,
            whiteSpace: 'nowrap',
            boxShadow: '0 2px 8px rgba(34,197,94,0.3)'
          }}>
            💎 {price} CHF
          </span>
        )}
        {isFree && (
          <span style={{
            position: 'absolute',
            bottom: '-5px',
            left: '50%',
            transform: 'translateX(-50%)',
            fontSize: '9px',
            padding: '2px 6px',
            borderRadius: '6px',
            background: 'rgba(255,255,255,0.15)',
            color: 'rgba(255,255,255,0.7)',
            fontWeight: 600,
            whiteSpace: 'nowrap'
          }}>
            Gratuit
          </span>
        )}
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
          {/* Play/Pause button */}
          <button
            onClick={togglePlay}
            style={{
              width: '38px',
              height: '38px',
              borderRadius: '50%',
              background: previewEnded
                ? 'rgba(255,255,255,0.15)'
                : `linear-gradient(135deg, ${accentColor}, ${accentColor}cc)`,
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              boxShadow: previewEnded ? 'none' : `0 0 15px ${accentColor}50, 0 2px 8px ${accentColor}40`,
              transition: 'transform 0.2s, box-shadow 0.2s',
              transform: isPlaying ? 'scale(1.05)' : 'scale(1)'
            }}
          >
            {previewEnded ? (
              <svg width="14" height="14" fill="#fff" viewBox="0 0 24 24">
                <polygon points="7 3 21 12 7 21 7 3" />
              </svg>
            ) : isPlaying ? (
              <svg width="14" height="14" fill="#fff" viewBox="0 0 24 24">
                <rect x="6" y="4" width="4" height="16" rx="1" />
                <rect x="14" y="4" width="4" height="16" rx="1" />
              </svg>
            ) : (
              <svg width="14" height="14" fill="#fff" viewBox="0 0 24 24">
                <polygon points="7 3 21 12 7 21 7 3" />
              </svg>
            )}
          </button>

          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ color: '#fff', fontSize: '14px', fontWeight: 700, margin: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {title}
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
              <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px' }}>
                {formatTime(currentTime)}
              </span>
              <span style={{ color: 'rgba(255,255,255,0.15)', fontSize: '12px' }}>/</span>
              <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px' }}>
                {formatTime(isPreview ? Math.min(maxPreviewTime, duration) : duration)}
              </span>
              {isPreview && !previewEnded && (
                <span style={{ fontSize: '10px', color: accentColor, fontWeight: 600, marginLeft: '4px' }}>
                  Aperçu
                </span>
              )}
            </div>
          </div>

          {/* Download button for free tracks */}
          {isFree && audioUrl && (
            <button
              onClick={handleDownload}
              title="Télécharger"
              style={{
                width: '32px', height: '32px', borderRadius: '8px', border: 'none',
                background: 'rgba(255,255,255,0.08)', color: 'rgba(255,255,255,0.6)',
                cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '14px', flexShrink: 0, transition: 'all 0.2s'
              }}
            >⬇️</button>
          )}
        </div>

        {/* Description */}
        {description && (
          <p style={{
            color: 'rgba(255,255,255,0.5)', fontSize: '11px', margin: '2px 0 4px 48px',
            lineHeight: '1.3', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            maxWidth: 'calc(100% - 60px)', display: 'block'
          }}>
            {description}
          </p>
        )}

        {/* Progress bar */}
        <div
          onClick={handleSeek}
          style={{
            width: '100%',
            height: '5px',
            borderRadius: '3px',
            background: previewEnded ? 'rgba(217,28,210,0.15)' : 'rgba(255,255,255,0.08)',
            cursor: previewEnded ? 'default' : 'pointer',
            position: 'relative',
            marginTop: '4px'
          }}
        >
          <div style={{
            width: previewEnded ? '100%' : `${progress}%`,
            height: '100%',
            borderRadius: '3px',
            background: previewEnded
              ? 'rgba(217,28,210,0.3)'
              : `linear-gradient(90deg, ${accentColor}, #8b5cf6)`,
            transition: 'width 0.1s linear',
            boxShadow: progress > 0 && !previewEnded ? `0 0 8px ${accentColor}60` : 'none',
            position: 'relative'
          }}>
            {/* Dot indicator */}
            {progress > 0 && !previewEnded && (
              <div style={{
                position: 'absolute',
                right: '-4px',
                top: '-2px',
                width: '9px',
                height: '9px',
                borderRadius: '50%',
                background: '#fff',
                boxShadow: `0 0 6px ${accentColor}80`,
                opacity: isHovered || isPlaying ? 1 : 0,
                transition: 'opacity 0.2s'
              }} />
            )}
          </div>
        </div>

        {/* v35: Preview ended overlay — message + buy button */}
        {isPreview && previewEnded && (
          <div style={{
            marginTop: '10px',
            padding: '12px',
            borderRadius: '12px',
            background: 'linear-gradient(135deg, rgba(217,28,210,0.1), rgba(139,92,246,0.08))',
            border: '1px solid rgba(217,28,210,0.2)',
            textAlign: 'center'
          }}>
            <p style={{
              color: 'rgba(255,255,255,0.7)', fontSize: '12px', margin: '0 0 8px 0', fontWeight: 500
            }}>
              🔒 Extrait de {maxPreviewTime}s terminé. Achetez pour écouter la suite.
            </p>
            {price > 0 && onBuyClick && (
              <button
                onClick={onBuyClick}
                style={{
                  width: '100%',
                  padding: '10px',
                  borderRadius: '10px',
                  background: `linear-gradient(135deg, ${accentColor}, #8b5cf6)`,
                  color: '#fff',
                  fontWeight: 700,
                  fontSize: '13px',
                  border: 'none',
                  cursor: 'pointer',
                  boxShadow: `0 0 20px ${accentColor}30`,
                  transition: 'transform 0.2s'
                }}
                onMouseEnter={(e) => { e.currentTarget.style.transform = 'translateY(-1px)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.transform = 'translateY(0)'; }}
              >
                🎵 Acheter {price} CHF
              </button>
            )}
            <button
              onClick={togglePlay}
              style={{
                marginTop: '6px', width: '100%', padding: '6px', borderRadius: '8px',
                background: 'transparent', border: '1px solid rgba(255,255,255,0.15)',
                color: 'rgba(255,255,255,0.5)', fontSize: '11px', cursor: 'pointer'
              }}
            >
              ↻ Réécouter l'aperçu
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default AudioPlayer;

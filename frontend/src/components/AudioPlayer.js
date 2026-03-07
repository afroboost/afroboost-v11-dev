/**
 * AudioPlayer Component v17.4
 * Lecteur audio premium style Spotify
 * - Miniature carrée + glow violet
 * - Barre de progression
 * - Mode preview 30s avec badge
 * - Bouton achat intégré
 */
import React, { useState, useRef, useEffect, useCallback } from 'react';

const AudioPlayer = ({
  audioUrl,
  previewUrl,
  title = 'Audio',
  thumbnail,
  duration: durationProp,
  price,
  accentColor = '#D91CD2',
  isPreview = false,
  onBuyClick
}) => {
  const audioRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(durationProp || 0);
  const [previewEnded, setPreviewEnded] = useState(false);

  const src = isPreview ? (previewUrl || audioUrl) : audioUrl;

  const formatTime = (s) => {
    if (!s || isNaN(s)) return '0:00';
    const min = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${min}:${sec.toString().padStart(2, '0')}`;
  };

  const togglePlay = useCallback(() => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play().catch(() => {});
      setIsPlaying(true);
      setPreviewEnded(false);
    }
  }, [isPlaying]);

  const handleTimeUpdate = () => {
    if (!audioRef.current) return;
    setCurrentTime(audioRef.current.currentTime);

    // Preview: stop at 30s
    if (isPreview && audioRef.current.currentTime >= 30) {
      audioRef.current.pause();
      setIsPlaying(false);
      setPreviewEnded(true);
    }
  };

  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(isPreview ? Math.min(30, audioRef.current.duration) : audioRef.current.duration);
    }
  };

  const handleSeek = (e) => {
    if (!audioRef.current) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const pct = x / rect.width;
    const maxTime = isPreview ? 30 : duration;
    audioRef.current.currentTime = pct * maxTime;
  };

  const handleEnded = () => {
    setIsPlaying(false);
    setCurrentTime(0);
  };

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
      }
    };
  }, []);

  const progress = duration > 0 ? (currentTime / (isPreview ? Math.min(30, duration) : duration)) * 100 : 0;

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '14px',
      padding: '12px',
      borderRadius: '14px',
      background: 'rgba(0,0,0,0.4)',
      border: '1px solid rgba(255,255,255,0.06)',
      position: 'relative',
      overflow: 'hidden'
    }}>
      {/* Glow effect */}
      <div style={{
        position: 'absolute',
        top: '-20px',
        left: '-20px',
        width: '80px',
        height: '80px',
        borderRadius: '50%',
        background: `radial-gradient(circle, ${accentColor}20, transparent)`,
        filter: 'blur(20px)',
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

      {/* Thumbnail */}
      <div style={{ position: 'relative', flexShrink: 0 }}>
        <div style={{
          width: '56px',
          height: '56px',
          borderRadius: '10px',
          background: thumbnail ? 'none' : `linear-gradient(135deg, ${accentColor}40, ${accentColor}10)`,
          border: `2px solid ${accentColor}50`,
          overflow: 'hidden',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: `0 0 20px ${accentColor}30`
        }}>
          {thumbnail ? (
            <img src={thumbnail} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          ) : (
            <span style={{ fontSize: '24px' }}>🎵</span>
          )}
        </div>
        {isPreview && (
          <span style={{
            position: 'absolute',
            top: '-4px',
            right: '-4px',
            fontSize: '9px',
            padding: '2px 5px',
            borderRadius: '4px',
            background: accentColor,
            color: '#fff',
            fontWeight: 700
          }}>
            30s
          </span>
        )}
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
          {/* Play/Pause */}
          <button
            onClick={togglePlay}
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '50%',
              background: `linear-gradient(135deg, ${accentColor}, ${accentColor}cc)`,
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              boxShadow: `0 2px 8px ${accentColor}40`
            }}
          >
            {isPlaying ? (
              <svg width="12" height="12" fill="#fff" viewBox="0 0 24 24">
                <rect x="6" y="4" width="4" height="16" rx="1" />
                <rect x="14" y="4" width="4" height="16" rx="1" />
              </svg>
            ) : (
              <svg width="12" height="12" fill="#fff" viewBox="0 0 24 24">
                <polygon points="6 3 20 12 6 21 6 3" />
              </svg>
            )}
          </button>

          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ color: '#fff', fontSize: '13px', fontWeight: 600, margin: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {title}
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px' }}>
                {formatTime(currentTime)}
              </span>
              <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: '11px' }}>/</span>
              <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px' }}>
                {formatTime(isPreview ? Math.min(30, duration) : duration)}
              </span>
              {isPreview && (
                <span style={{ fontSize: '10px', color: accentColor, fontWeight: 600 }}>
                  📻 Aperçu
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Progress bar */}
        <div
          onClick={handleSeek}
          style={{
            width: '100%',
            height: '4px',
            borderRadius: '2px',
            background: 'rgba(255,255,255,0.1)',
            cursor: 'pointer',
            position: 'relative',
            marginTop: '4px'
          }}
        >
          <div style={{
            width: `${progress}%`,
            height: '100%',
            borderRadius: '2px',
            background: `linear-gradient(90deg, ${accentColor}, ${accentColor}aa)`,
            transition: 'width 0.1s linear'
          }} />
        </div>

        {/* Buy button for preview mode */}
        {isPreview && previewEnded && price && onBuyClick && (
          <button
            onClick={onBuyClick}
            style={{
              marginTop: '8px',
              width: '100%',
              padding: '8px',
              borderRadius: '8px',
              background: `linear-gradient(135deg, ${accentColor}, #8b5cf6)`,
              color: '#fff',
              fontWeight: 600,
              fontSize: '12px',
              border: 'none',
              cursor: 'pointer'
            }}
          >
            🔓 Acheter {price} CHF
          </button>
        )}
      </div>
    </div>
  );
};

export default AudioPlayer;

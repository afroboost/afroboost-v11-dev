/**
 * AudioPlayer Component v17.5
 * Lecteur audio premium style Spotify + Glassmorphism
 * - Large thumbnail avec glow neon
 * - Barre de progression fluide
 * - Mode preview configurable avec badge
 * - Bouton achat intégré
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

    if (isPreview && audioRef.current.currentTime >= maxPreviewTime) {
      audioRef.current.pause();
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
    if (!audioRef.current) return;
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
        alignItems: 'center',
        gap: '16px',
        padding: '16px',
        borderRadius: '18px',
        background: 'rgba(10,5,20,0.6)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        border: `1px solid ${isHovered ? `${accentColor}50` : 'rgba(255,255,255,0.06)'}`,
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

      {/* Large Thumbnail with neon glow */}
      <div style={{ position: 'relative', flexShrink: 0 }}>
        <div style={{
          width: '80px',
          height: '80px',
          borderRadius: '14px',
          background: thumbnail ? 'none' : `linear-gradient(135deg, ${accentColor}40, ${accentColor}10)`,
          border: `2px solid ${accentColor}60`,
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
          {/* Play overlay on hover */}
          <div style={{
            position: 'absolute',
            inset: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            opacity: isHovered ? 1 : 0,
            transition: 'opacity 0.2s',
            borderRadius: '12px'
          }}>
            {isPlaying ? (
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
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
          {/* Play/Pause button */}
          <button
            onClick={togglePlay}
            style={{
              width: '38px',
              height: '38px',
              borderRadius: '50%',
              background: `linear-gradient(135deg, ${accentColor}, ${accentColor}cc)`,
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              boxShadow: `0 0 15px ${accentColor}50, 0 2px 8px ${accentColor}40`,
              transition: 'transform 0.2s, box-shadow 0.2s',
              transform: isPlaying ? 'scale(1.05)' : 'scale(1)'
            }}
          >
            {isPlaying ? (
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
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px' }}>
                {formatTime(currentTime)}
              </span>
              <span style={{ color: 'rgba(255,255,255,0.15)', fontSize: '12px' }}>/</span>
              <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px' }}>
                {formatTime(isPreview ? Math.min(maxPreviewTime, duration) : duration)}
              </span>
              {isPreview && (
                <span style={{ fontSize: '10px', color: accentColor, fontWeight: 600, marginLeft: '4px' }}>
                  Aperçu
                </span>
              )}
              {price > 0 && (
                <span style={{
                  fontSize: '10px',
                  color: '#22c55e',
                  fontWeight: 700,
                  marginLeft: 'auto',
                  background: 'rgba(34,197,94,0.1)',
                  padding: '1px 6px',
                  borderRadius: '4px'
                }}>
                  {price} CHF
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
            height: '5px',
            borderRadius: '3px',
            background: 'rgba(255,255,255,0.08)',
            cursor: 'pointer',
            position: 'relative',
            marginTop: '4px'
          }}
        >
          <div style={{
            width: `${progress}%`,
            height: '100%',
            borderRadius: '3px',
            background: `linear-gradient(90deg, ${accentColor}, #8b5cf6)`,
            transition: 'width 0.1s linear',
            boxShadow: progress > 0 ? `0 0 8px ${accentColor}60` : 'none',
            position: 'relative'
          }}>
            {/* Dot indicator */}
            {progress > 0 && (
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

        {/* Buy button for preview mode */}
        {isPreview && previewEnded && price > 0 && onBuyClick && (
          <button
            onClick={onBuyClick}
            style={{
              marginTop: '10px',
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
            Acheter {price} CHF
          </button>
        )}
      </div>
    </div>
  );
};

export default AudioPlayer;

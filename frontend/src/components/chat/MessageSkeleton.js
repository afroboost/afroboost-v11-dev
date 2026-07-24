/**
 * MessageSkeleton.js - Animation de chargement élégante
 * 
 * Affiche 3-4 bulles de messages animées (pulsation douce)
 * pendant le chargement initial de l'historique.
 * 
 * Design: Ultra-minimaliste avec animation fade in/out
 */

import React, { memo } from 'react';

// Composant de bulle skeleton individuelle
const SkeletonBubble = ({ width, isRight, delay = 0, hasMedia = false, hasCta = false }) => (
  <div
    style={{
      display: 'flex',
      justifyContent: isRight ? 'flex-end' : 'flex-start',
      marginBottom: '12px',
      opacity: 0,
      animation: `skeletonFadeIn 0.3s ease-out ${delay}ms forwards`
    }}
  >
    <div
      style={{
        width: width,
        display: 'flex',
        flexDirection: 'column',
        gap: '8px'
      }}
    >
      {/* Zone média (si hasMedia) */}
      {hasMedia && (
        <div
          style={{
            width: '100%',
            height: '120px',
            borderRadius: '12px',
            background: 'linear-gradient(135deg, rgba(147, 51, 234, 0.1), rgba(99, 102, 241, 0.1))',
            animation: 'skeletonPulse 1.5s ease-in-out infinite',
            animationDelay: `${delay}ms`
          }}
        />
      )}
      
      {/* Bulle de texte */}
      <div
        style={{
          width: hasMedia ? '80%' : '100%',
          height: '40px',
          borderRadius: isRight ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
          background: isRight 
            ? 'linear-gradient(135deg, rgba(var(--primary-rgb, 217, 28, 210), 0.15), rgba(139, 92, 246, 0.15))'
            : 'rgba(255, 255, 255, 0.08)',
          animation: 'skeletonPulse 1.5s ease-in-out infinite',
          animationDelay: `${delay}ms`
        }}
      />
      
      {/* Bouton CTA (si hasCta) */}
      {hasCta && (
        <div
          style={{
            width: '140px',
            height: '36px',
            borderRadius: '20px',
            background: 'linear-gradient(135deg, rgba(147, 51, 234, 0.2), rgba(var(--primary-rgb, 217, 28, 210), 0.2))',
            animation: 'skeletonPulse 1.5s ease-in-out infinite',
            animationDelay: `${delay + 50}ms`,
            alignSelf: 'center'
          }}
        />
      )}
    </div>
  </div>
);

// Composant principal avec plusieurs bulles
const MessageSkeleton = ({ count = 4, includeMedia = false }) => {
  // Configuration des bulles pour un aspect naturel
  // Inclut une bulle avec média+CTA pour éviter le "saut" au chargement
  const bubbles = [
    { width: '65%', isRight: false, delay: 0 },
    { width: '45%', isRight: true, delay: 100 },
    // Bulle avec média et CTA (simule un message enrichi)
    { width: '280px', isRight: false, delay: 200, hasMedia: includeMedia, hasCta: includeMedia },
    { width: '55%', isRight: true, delay: 300 },
  ].slice(0, count);

  return (
    <div 
      style={{ 
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '4px'
      }}
      data-testid="message-skeleton"
    >
      {/* Indicateur de chargement discret */}
      <div 
        style={{
          textAlign: 'center',
          marginBottom: '16px',
          fontSize: '12px',
          color: 'rgba(255, 255, 255, 0.4)',
          animation: 'skeletonPulse 1.5s ease-in-out infinite'
        }}
      >
        Chargement de l'historique...
      </div>

      {/* Bulles skeleton */}
      {bubbles.map((bubble, idx) => (
        <SkeletonBubble 
          key={idx}
          width={bubble.width}
          isRight={bubble.isRight}
          delay={bubble.delay}
        />
      ))}

      {/* Styles CSS inline pour les animations */}
      <style>{`
        @keyframes skeletonPulse {
          0%, 100% {
            opacity: 0.4;
          }
          50% {
            opacity: 0.8;
          }
        }
        
        @keyframes skeletonFadeIn {
          from {
            opacity: 0;
            transform: translateY(8px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  );
};

export default memo(MessageSkeleton);

import React, { useState, useEffect } from 'react';

/**
 * PaymentSuccessPage - Page de succès après paiement Stripe
 * Design cohérent avec le thème Afroboost (fond sombre, effet glow néon)
 */
const PaymentSuccessPage = ({ 
  reservation, 
  onClose, 
  t = (key) => key // Fonction de traduction par défaut
}) => {
  const [showConfetti, setShowConfetti] = useState(true);
  
  useEffect(() => {
    // Désactiver les confettis après 5 secondes
    const timer = setTimeout(() => setShowConfetti(false), 5000);
    return () => clearTimeout(timer);
  }, []);

  // Textes par défaut si pas de traduction
  const texts = {
    title: t('paymentSuccessTitle') || 'Paiement réussi !',
    subtitle: t('paymentSuccessSubtitle') || 'Bienvenue dans l\'expérience Afroboost',
    description: t('paymentSuccessDesc') || 'Votre réservation a été confirmée. Vous recevrez un email de confirmation avec tous les détails.',
    reservationCode: t('reservationCode') || 'Code de réservation',
    course: t('course') || 'Cours',
    amount: t('amount') || 'Montant payé',
    accessButton: t('accessCourses') || 'Accéder à mes cours',
    shareButton: t('shareSuccess') || 'Partager'
  };

  return (
    <div 
      className="payment-success-page"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 9999,
        background: 'linear-gradient(180deg, #000000 0%, #0a0015 50%, #1a0a2e 100%)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
        overflow: 'auto'
      }}
      data-testid="payment-success-page"
    >
      {/* Effet de lueur en arrière-plan */}
      <div 
        style={{
          position: 'absolute',
          top: '20%',
          left: '50%',
          transform: 'translateX(-50%)',
          width: '400px',
          height: '400px',
          background: 'radial-gradient(circle, rgba(var(--primary-rgb, 217, 28, 210), 0.15) 0%, transparent 70%)',
          pointerEvents: 'none',
          filter: 'blur(60px)'
        }}
      />
      
      {/* Confettis animés */}
      {showConfetti && (
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: '100%', overflow: 'hidden', pointerEvents: 'none' }}>
          {[...Array(30)].map((_, i) => (
            <div
              key={i}
              style={{
                position: 'absolute',
                top: '-10px',
                left: `${Math.random() * 100}%`,
                width: `${8 + Math.random() * 8}px`,
                height: `${8 + Math.random() * 8}px`,
                background: ['var(--primary-color, #D91CD2)', '#8b5cf6', '#06b6d4', '#f59e0b', '#10b981'][Math.floor(Math.random() * 5)],
                borderRadius: Math.random() > 0.5 ? '50%' : '2px',
                animation: `confetti-fall ${3 + Math.random() * 2}s linear forwards`,
                animationDelay: `${Math.random() * 2}s`,
                opacity: 0.8
              }}
            />
          ))}
        </div>
      )}
      
      {/* Contenu principal */}
      <div 
        style={{
          position: 'relative',
          maxWidth: '500px',
          width: '100%',
          textAlign: 'center',
          zIndex: 1
        }}
      >
        {/* Icône de succès animée */}
        <div 
          style={{
            width: '100px',
            height: '100px',
            margin: '0 auto 24px',
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 0 40px rgba(16, 185, 129, 0.4)',
            animation: 'success-pulse 2s ease-in-out infinite'
          }}
          data-testid="success-icon"
        >
          <svg width="50" height="50" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
        </div>
        
        {/* Titre */}
        <h1 
          style={{
            fontSize: '2.5rem',
            fontWeight: 'bold',
            color: 'white',
            marginBottom: '12px',
            textShadow: '0 0 20px rgba(var(--primary-rgb, 217, 28, 210), 0.5)'
          }}
          data-testid="success-title"
        >
          {texts.title}
        </h1>
        
        {/* Sous-titre */}
        <p 
          style={{
            fontSize: '1.25rem',
            color: 'var(--primary-color, #D91CD2)',
            marginBottom: '24px',
            fontWeight: '500'
          }}
          data-testid="success-subtitle"
        >
          {texts.subtitle}
        </p>
        
        {/* Description */}
        <p 
          style={{
            fontSize: '1rem',
            color: 'rgba(255, 255, 255, 0.7)',
            marginBottom: '32px',
            lineHeight: '1.6'
          }}
        >
          {texts.description}
        </p>
        
        {/* Carte de détails de réservation */}
        {reservation && (
          <div 
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              backdropFilter: 'blur(10px)',
              borderRadius: '16px',
              padding: '24px',
              marginBottom: '32px',
              border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.3)',
              boxShadow: '0 0 30px rgba(var(--primary-rgb, 217, 28, 210), 0.1)'
            }}
            data-testid="reservation-details"
          >
            {/* Code de réservation */}
            <div style={{ marginBottom: '16px' }}>
              <p style={{ fontSize: '0.85rem', color: 'rgba(255, 255, 255, 0.5)', marginBottom: '4px' }}>
                {texts.reservationCode}
              </p>
              <p 
                style={{ 
                  fontSize: '1.5rem', 
                  fontWeight: 'bold', 
                  color: 'var(--primary-color, #D91CD2)',
                  fontFamily: 'monospace',
                  letterSpacing: '2px'
                }}
                data-testid="reservation-code"
              >
                {reservation.reservationCode || 'N/A'}
              </p>
            </div>
            
            {/* Détails du cours */}
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: '1fr 1fr', 
              gap: '16px',
              textAlign: 'left'
            }}>
              <div>
                <p style={{ fontSize: '0.85rem', color: 'rgba(255, 255, 255, 0.5)', marginBottom: '4px' }}>
                  {texts.course}
                </p>
                <p style={{ fontSize: '1rem', color: 'white', fontWeight: '500' }}>
                  {reservation.courseName || reservation.offerName || 'N/A'}
                </p>
              </div>
              <div>
                <p style={{ fontSize: '0.85rem', color: 'rgba(255, 255, 255, 0.5)', marginBottom: '4px' }}>
                  {texts.amount}
                </p>
                <p style={{ fontSize: '1rem', color: '#10b981', fontWeight: 'bold' }}>
                  CHF {reservation.totalPrice || '0.00'}
                </p>
              </div>
            </div>
          </div>
        )}
        
        {/* Boutons d'action */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {/* Bouton principal - Accéder aux cours */}
          <button
            onClick={onClose}
            style={{
              width: '100%',
              padding: '16px 32px',
              fontSize: '1.1rem',
              fontWeight: 'bold',
              color: 'white',
              background: 'linear-gradient(135deg, var(--primary-color, #D91CD2) 0%, #8b5cf6 100%)',
              border: 'none',
              borderRadius: '12px',
              cursor: 'pointer',
              boxShadow: '0 4px 20px rgba(var(--primary-rgb, 217, 28, 210), 0.4)',
              transition: 'all 0.3s ease',
              textTransform: 'uppercase',
              letterSpacing: '1px'
            }}
            onMouseEnter={(e) => {
              e.target.style.transform = 'translateY(-2px)';
              e.target.style.boxShadow = '0 6px 30px rgba(var(--primary-rgb, 217, 28, 210), 0.6)';
            }}
            onMouseLeave={(e) => {
              e.target.style.transform = 'translateY(0)';
              e.target.style.boxShadow = '0 4px 20px rgba(var(--primary-rgb, 217, 28, 210), 0.4)';
            }}
            data-testid="access-courses-btn"
          >
            🎧 {texts.accessButton}
          </button>
        </div>
      </div>
      
      {/* Styles d'animation */}
      <style>{`
        @keyframes success-pulse {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.05); }
        }
        
        @keyframes confetti-fall {
          0% {
            transform: translateY(0) rotate(0deg);
            opacity: 1;
          }
          100% {
            transform: translateY(100vh) rotate(720deg);
            opacity: 0;
          }
        }
      `}</style>
    </div>
  );
};

export default PaymentSuccessPage;

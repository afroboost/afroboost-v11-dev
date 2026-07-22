/**
 * CreditsGate Component v13.2
 * Composant réutilisable pour bloquer l'accès aux services premium
 * quand les crédits sont insuffisants
 */
import React from 'react';
import SvgIcon from '../SvgIcon';

const CreditsGate = ({
  serviceName,
  requiredCredits,
  currentCredits,
  onGoToBoutique,
  testId
}) => {
  return (
    <div className="text-center py-16" data-testid={testId || 'credits-lock'}>
      <div className="text-6xl mb-6"><SvgIcon name="lock" size={60} /></div>
      <h2 className="text-2xl font-bold text-white mb-4">Crédits insuffisants</h2>
      <p className="text-white/50 mb-2">
        Ce service premium nécessite{' '}
        <span style={{ color: '#D91CD2', fontWeight: 'bold' }}>
          {requiredCredits} crédit(s)
        </span>
      </p>
      <p className="text-white/30 text-sm mb-8">
        Votre solde actuel:{' '}
        <span className="text-red-400 font-bold">{currentCredits}</span> crédits
      </p>
      <button
        onClick={onGoToBoutique}
        className="px-8 py-3 text-white font-medium transition-all hover:opacity-80"
        style={{ 
          background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
          borderRadius: '8px'
        }}
        data-testid={`go-to-boutique-${serviceName}`}
      >
        <span className="inline-flex items-center gap-1.5">
          <SvgIcon name="diamond" size={16} /> Recharger mes crédits
        </span>
      </button>
    </div>
  );
};

export default CreditsGate;

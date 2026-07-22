/**
 * StripeConnectTab Component v13.2
 * Section Stripe Connect et personnalisation marque blanche
 * Extrait de CoachDashboard.js pour alléger le code
 */
import React from 'react';
import axios from 'axios';
import SvgIcon from '../SvgIcon';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

const StripeConnectTab = ({
  stripeConnectStatus,
  stripeConnectLoading,
  onStripeConnect,
  coachPlatformName,
  setCoachPlatformName,
  coachEmail
}) => {
  const handleSavePlatformName = async () => {
    try {
      await axios.put(`${BACKEND_URL}/api/coach/update-profile`, {
        platform_name: coachPlatformName
      }, { headers: { 'X-User-Email': coachEmail } });
      alert('✓ Nom de plateforme enregistré !');
    } catch (err) {
      alert('Erreur lors de la sauvegarde');
    }
  };

  return (
    <div className="space-y-6" data-testid="stripe-tab">
      <div className="glass rounded-xl p-6" style={{ border: '1px solid rgba(217, 28, 210, 0.3)' }}>
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2"><SvgIcon name="creditCard" size={20} /> Stripe Connect</h2>
        <p className="text-white/70 mb-6">
          Connectez votre compte Stripe pour recevoir directement les paiements de vos clients.
        </p>
        
        {/* Statut actuel */}
        <div className="glass rounded-lg p-4 mb-6" style={{ background: 'rgba(255,255,255,0.05)' }}>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-white font-medium">Statut du compte</h3>
              <p className="text-white/50 text-sm mt-1">
                {stripeConnectStatus?.connected 
                  ? stripeConnectStatus?.charges_enabled 
                    ? 'Compte vérifié et prêt à recevoir des paiements' 
                    : 'Compte en cours de vérification'
                  : 'Non connecté'}
              </p>
            </div>
            <span className={`px-3 py-1 rounded-full text-sm font-medium ${
              stripeConnectStatus?.connected 
                ? stripeConnectStatus?.charges_enabled 
                  ? 'bg-green-500/20 text-green-400' 
                  : 'bg-yellow-500/20 text-yellow-400'
                : 'bg-red-500/20 text-red-400'
            }`}>
              {stripeConnectStatus?.connected 
                ? stripeConnectStatus?.charges_enabled
                  ? <span className="inline-flex items-center gap-1.5"><SvgIcon name="check" size={14} /> Actif</span>
                  : <span className="inline-flex items-center gap-1.5"><SvgIcon name="loader" size={14} className="animate-spin" /> En attente</span>
                : <span className="inline-flex items-center gap-1.5"><SvgIcon name="close" size={14} /> Déconnecté</span>}
            </span>
          </div>
        </div>
        
        {/* Bouton de connexion */}
        <button
          onClick={onStripeConnect}
          disabled={stripeConnectLoading}
          className="w-full py-3 rounded-lg text-white font-semibold transition-all hover:scale-105 disabled:opacity-50"
          style={{ background: 'linear-gradient(135deg, #635BFF, #8b5cf6)' }}
          data-testid="stripe-connect-tab-btn"
        >
          {stripeConnectLoading 
            ? 'Chargement...' 
            : stripeConnectStatus?.connected 
              ? 'Gérer mon compte Stripe' 
              : 'Connecter mon compte Stripe'}
        </button>
        
        {/* Info */}
        <div className="mt-6 p-4 rounded-lg" style={{ background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)' }}>
          <h4 className="text-white font-medium mb-2 flex items-center gap-2"><SvgIcon name="lightbulb" size={16} /> Comment ça marche ?</h4>
          <ul className="text-white/70 text-sm space-y-1 list-disc pl-5">
            <li>Les paiements de vos clients seront versés sur votre compte</li>
            <li>Une commission plateforme s'applique sur chaque transaction</li>
            <li>Les virements sont automatiques sous 2-7 jours</li>
          </ul>
        </div>
      </div>
      
      {/* === Personnalisation Marque Blanche === */}
      <div className="glass rounded-xl p-6" style={{ border: '1px solid rgba(217, 28, 210, 0.3)' }}>
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2"><SvgIcon name="palette" size={20} /> Personnalisation</h2>
        <p className="text-white/70 mb-4">
          Personnalisez votre espace avec votre propre marque.
        </p>
        
        <div className="space-y-4">
          <div>
            <label className="block text-white/70 text-sm mb-2">Nom de ma plateforme</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={coachPlatformName || ''}
                onChange={(e) => setCoachPlatformName(e.target.value)}
                placeholder="Ex: Mon Studio Fitness"
                className="flex-1 px-4 py-2 rounded-lg bg-white/5 text-white border border-white/20 focus:border-purple-500 focus:outline-none"
                data-testid="platform-name-input"
              />
              <button
                onClick={handleSavePlatformName}
                className="px-4 py-2 rounded-lg text-white font-medium"
                style={{ background: 'linear-gradient(135deg, #d91cd2, #8b5cf6)' }}
                data-testid="save-platform-name-btn"
              >
                Enregistrer
              </button>
            </div>
            <p className="text-white/50 text-xs mt-1">Ce nom s'affichera en haut de votre dashboard</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StripeConnectTab;

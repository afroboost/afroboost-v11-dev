/**
 * PageVenteTab Component v13.5
 * Section "Ma Page de Vente" - QR Code, liens partage, configuration paiement
 * Extrait de CoachDashboard.js
 */
import React from 'react';
import { QRCodeSVG } from 'qrcode.react';

const PageVenteTab = ({
  coachVitrineUrl,
  linkCopied,
  onCopyLink,
  paymentLinks,
  setPaymentLinks,
  paymentSaveStatus,
  t
}) => {
  return (
    <div className="space-y-6" data-testid="page-vente-tab">
      {/* Bloc principal - Ma Page de Vente */}
      <div className="card-gradient rounded-xl p-6">
        <h2 className="font-semibold text-white mb-2" style={{ fontSize: '20px' }}>🏪 Ma Page de Vente</h2>
        <p className="text-white/60 text-sm mb-6">
          Partagez votre page personnalisée avec vos clients pour qu'ils puissent réserver et payer.
        </p>
        
        {/* URL de la page de vente */}
        <div 
          className="rounded-lg p-4 mb-6"
          style={{ background: 'rgba(217, 28, 210, 0.1)', border: '1px solid rgba(217, 28, 210, 0.3)' }}
        >
          <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
            <div className="flex-1">
              <h4 className="text-white font-medium mb-1">🔗 Votre lien unique</h4>
              <p className="text-purple-400 text-sm break-all" data-testid="page-vente-url">
                {coachVitrineUrl || 'Chargement...'}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={onCopyLink}
                className="px-4 py-2 rounded-lg text-white text-sm font-semibold transition-all hover:scale-105"
                style={{ background: linkCopied ? 'rgba(34, 197, 94, 0.3)' : 'linear-gradient(135deg, #d91cd2, #8b5cf6)' }}
                data-testid="copy-page-vente-link"
              >
                {linkCopied ? '✓ Copié' : '📋 Copier'}
              </button>
              <button
                onClick={() => coachVitrineUrl && window.open(coachVitrineUrl, '_blank')}
                className="px-4 py-2 rounded-lg text-white text-sm font-semibold"
                style={{ background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)' }}
                data-testid="preview-page-vente"
              >
                👁️ Voir
              </button>
            </div>
          </div>
        </div>
        
        {/* QR Code */}
        {coachVitrineUrl && (
          <div className="flex justify-center mb-6">
            <div className="bg-white rounded-lg p-4" data-testid="page-vente-qr">
              <QRCodeSVG 
                value={coachVitrineUrl}
                size={150}
                bgColor="#FFFFFF"
                fgColor="#1a1a2e"
                level="H"
                includeMargin={true}
              />
            </div>
          </div>
        )}
        
        <p className="text-white/40 text-xs text-center">
          💡 Imprimez le QR Code pour vos flyers ou affichez-le dans votre salle !
        </p>
      </div>
      
      {/* Bloc secondaire - Liens de paiement (collapsible) */}
      <details className="card-gradient rounded-xl overflow-hidden">
        <summary 
          className="p-4 cursor-pointer text-white font-medium flex justify-between items-center"
          style={{ background: 'rgba(255,255,255,0.03)' }}
        >
          <div className="flex items-center gap-3">
            <span>⚙️ Configuration des liens de paiement (optionnel)</span>
            {paymentSaveStatus && (
              <span 
                className="px-2 py-0.5 rounded-full text-xs"
                style={{
                  background: paymentSaveStatus === 'saved' ? 'rgba(34, 197, 94, 0.2)' : 
                             paymentSaveStatus === 'error' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(147, 51, 234, 0.2)',
                  color: paymentSaveStatus === 'saved' ? '#22c55e' : 
                         paymentSaveStatus === 'error' ? '#ef4444' : '#a855f7'
                }}
                data-testid="payment-save-status"
              >
                {paymentSaveStatus === 'saving' && '⏳'}
                {paymentSaveStatus === 'saved' && '✓'}
                {paymentSaveStatus === 'error' && '⚠️'}
              </span>
            )}
          </div>
          <span className="text-white/40">▼</span>
        </summary>
        <div className="p-6 space-y-4">
          <div>
            <label className="block mb-2 text-white text-sm">{t('stripeLink')}</label>
            <input 
              type="url" 
              value={paymentLinks.stripe} 
              onChange={e => setPaymentLinks({ ...paymentLinks, stripe: e.target.value })} 
              className="w-full px-4 py-3 rounded-lg neon-input" 
              placeholder="https://buy.stripe.com/..." 
              data-testid="payment-stripe-input" 
            />
          </div>
          <div>
            <label className="block mb-2 text-white text-sm">{t('paypalLink')}</label>
            <input 
              type="url" 
              value={paymentLinks.paypal} 
              onChange={e => setPaymentLinks({ ...paymentLinks, paypal: e.target.value })} 
              className="w-full px-4 py-3 rounded-lg neon-input" 
              placeholder="https://paypal.me/..." 
              data-testid="payment-paypal-input" 
            />
          </div>
          <div>
            <label className="block mb-2 text-white text-sm">{t('twintLink')}</label>
            <input 
              type="url" 
              value={paymentLinks.twint} 
              onChange={e => setPaymentLinks({ ...paymentLinks, twint: e.target.value })} 
              className="w-full px-4 py-3 rounded-lg neon-input" 
              placeholder="https://..." 
              data-testid="payment-twint-input" 
            />
          </div>
          <div>
            <label className="block mb-2 text-white text-sm">{t('coachWhatsapp')}</label>
            <input 
              type="tel" 
              value={paymentLinks.coachWhatsapp} 
              onChange={e => setPaymentLinks({ ...paymentLinks, coachWhatsapp: e.target.value })} 
              className="w-full px-4 py-3 rounded-lg neon-input" 
              placeholder="+41791234567" 
              data-testid="payment-whatsapp-input" 
            />
          </div>
          
          {/* Section Notifications automatiques */}
          <div className="mt-6 pt-6 border-t border-purple-500/30">
            <h3 className="text-white text-sm font-semibold mb-4">🔔 Notifications automatiques</h3>
            <p className="text-xs mb-4" style={{ color: 'rgba(255,255,255,0.5)' }}>
              Recevez une notification par email et/ou WhatsApp à chaque nouvelle réservation.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block mb-2 text-white text-xs opacity-70">📧 Email pour les alertes</label>
                <input 
                  type="email" 
                  value={paymentLinks.coachNotificationEmail || ''} 
                  onChange={e => setPaymentLinks({ ...paymentLinks, coachNotificationEmail: e.target.value })} 
                  className="w-full px-4 py-3 rounded-lg neon-input text-sm" 
                  placeholder="coach@exemple.com"
                  data-testid="coach-notification-email"
                />
              </div>
              <div>
                <label className="block mb-2 text-white text-xs opacity-70">📱 WhatsApp pour les alertes</label>
                <input 
                  type="tel" 
                  value={paymentLinks.coachNotificationPhone || ''} 
                  onChange={e => setPaymentLinks({ ...paymentLinks, coachNotificationPhone: e.target.value })} 
                  className="w-full px-4 py-3 rounded-lg neon-input text-sm" 
                  placeholder="+41791234567"
                  data-testid="coach-notification-phone"
                />
              </div>
            </div>
          </div>

          {/* Indication auto-save */}
          <div className="mt-4 p-3 rounded-lg" style={{ background: 'rgba(34, 197, 94, 0.1)', border: '1px solid rgba(34, 197, 94, 0.2)' }}>
            <p className="text-green-400 text-xs flex items-center gap-2">
              <span>✓</span> Sauvegarde automatique - Vos liens sont enregistrés à chaque modification
            </p>
          </div>
        </div>
      </details>
    </div>
  );
};

export default PageVenteTab;

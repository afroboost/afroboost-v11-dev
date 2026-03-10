/**
 * CreditBoutique Component v13.3 (V93)
 * Section d'achat de packs de crédits pour les partenaires
 * Extrait de CoachDashboard.js pour alléger le code
 */
import React from 'react';

const CreditBoutique = ({
  coachCredits,
  creditPacks,
  loadingPacks,
  purchasingPack,
  onBuyPack,
  isSuperAdmin,
  servicePrices
}) => {
  return (
    <div className="space-y-6" data-testid="boutique-tab">
      {/* Header avec solde actuel - v12.1 Design Premium Sans Cadre */}
      <div className="text-center py-6" style={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
        <div className="text-white/50 text-sm mb-2">Votre solde actuel</div>
        <div className="text-4xl font-bold" style={{ color: '#D91CD2' }}>
          {coachCredits === -1 ? '∞' : coachCredits} crédits
        </div>
        {coachCredits !== -1 && coachCredits < 10 && (
          <div className="text-yellow-400 text-sm mt-2">
            ⚠️ Solde faible - Rechargez pour continuer à utiliser les services
          </div>
        )}
      </div>

      {/* v93: Service credit costs - read-only for partners */}
      {servicePrices && (
        <div style={{
          background: 'rgba(10,10,15,0.6)',
          border: '1px solid rgba(217,28,210,0.2)',
          borderRadius: '12px',
          padding: '16px',
          marginBottom: '16px'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <h3 style={{ color: '#D91CD2', fontSize: '14px', fontWeight: 'bold', margin: 0 }}>
              {isSuperAdmin ? '\u2699\ufe0f Tarifs des services (modifiable)' : '\ud83d\udcb0 Co\u00fbt des services'}
            </h3>
            {!isSuperAdmin && (
              <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '11px' }}>\ud83d\udd12 D\u00e9fini par l'admin</span>
            )}
          </div>
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            {[
              { key: 'campaign', label: 'Campagne Email', icon: '\ud83d\udce7' },
              { key: 'ai_conversation', label: 'Conversation IA', icon: '\ud83e\udd16' },
              { key: 'promo_code', label: 'Code Promo', icon: '\ud83c\udfab' }
            ].map(s => (
              <div key={s.key} style={{
                flex: '1 1 100px',
                background: 'rgba(217,28,210,0.08)',
                borderRadius: '8px',
                padding: '10px',
                textAlign: 'center'
              }}>
                <div style={{ fontSize: '20px', marginBottom: '4px' }}>{s.icon}</div>
                <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: '10px', marginBottom: '4px' }}>{s.label}</div>
                <div style={{ color: '#D91CD2', fontWeight: 'bold', fontSize: '16px' }}>
                  {servicePrices[s.key] || 1} cr.
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {/* Liste des packs disponibles */}
      <div>
        <h2 className="text-xl font-bold text-white mb-6">Choisissez votre pack</h2>
        
        {loadingPacks ? (
          <div className="text-center py-8 text-white/50">Chargement...</div>
        ) : creditPacks.length === 0 ? (
          <div className="text-center py-8 text-white/50">
            Aucun pack disponible pour le moment
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {creditPacks.map((pack, index) => (
              <div 
                key={pack.id}
                className="relative py-6 transition-all hover:scale-105"
                style={{ 
                  borderBottom: '1px solid rgba(255,255,255,0.1)',
                  borderLeft: index === 1 ? '2px solid #D91CD2' : 'none'
                }}
                data-testid={`pack-${pack.id}`}
              >
                {/* Badge populaire pour le 2ème pack */}
                {index === 1 && (
                  <div 
                    className="absolute -top-3 left-0 text-xs px-3 py-1 text-white"
                    style={{ background: '#D91CD2', borderRadius: '4px' }}
                  >
                    ⭐ Populaire
                  </div>
                )}
                
                <div className="text-center">
                  <div className="text-3xl font-bold text-white mb-2">
                    {pack.credits}
                  </div>
                  <div className="text-white/50 text-sm mb-4">crédits</div>
                  
                  <div className="text-2xl font-bold mb-1" style={{ color: '#D91CD2' }}>
                    {pack.price} CHF
                  </div>
                  
                  {pack.description && (
                    <div className="text-white/40 text-xs mb-4">{pack.description}</div>
                  )}
                  
                  <button
                    onClick={() => onBuyPack(pack)}
                    disabled={purchasingPack === pack.id}
                    className="w-full py-3 text-white font-medium transition-all hover:opacity-80 disabled:opacity-50"
                    style={{ 
                      background: purchasingPack === pack.id 
                        ? 'rgba(255,255,255,0.1)' 
                        : 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
                      borderRadius: '8px'
                    }}
                    data-testid={`buy-pack-${pack.id}`}
                  >
                    {purchasingPack === pack.id ? 'Redirection...' : 'Acheter'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Info paiement */}
      <div className="text-center py-6" style={{ borderTop: '1px solid rgba(255,255,255,0.1)' }}>
        <div className="flex items-center justify-center gap-4 text-white/40 text-xs">
          <span>💳 Paiement sécurisé</span>
          <span>•</span>
          <span>⚡ Crédits instantanés</span>
          <span>•</span>
          <span>🔒 Stripe</span>
        </div>
      </div>
    </div>
  );
};

export default CreditBoutique;

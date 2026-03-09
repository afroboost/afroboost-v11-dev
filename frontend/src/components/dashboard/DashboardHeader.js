/**
 * DashboardHeader Component v13.6
 * En-tête du dashboard avec cartes de statistiques et navigation onglets
 * Extrait de CoachDashboard.js
 */
import React from 'react';

// Icônes
const ShareIcon = () => (
  <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
  </svg>
);

const CheckIcon = () => (
  <svg className="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
  </svg>
);

const StarIcon = () => (
  <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 2L9 9l-7 2 5 5-1 7 6-3 6 3-1-7 5-5-7-2-3-7z" />
  </svg>
);

const ExternalLinkIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
    <polyline points="15 3 21 3 21 9"></polyline>
    <line x1="10" y1="14" x2="21" y2="3"></line>
  </svg>
);

const DashboardHeader = ({
  // Coach info
  coachUser,
  coachPlatformName,
  coachCredits,
  isSuperAdmin,
  // Stats
  totalReservations,
  totalContacts,
  // Stripe
  stripeConnectStatus,
  stripeConnectLoading,
  onStripeConnect,
  // Share
  linkCopied,
  onShareLink,
  // Admin
  onOpenAdminPanel,
  platformSettings,
  onToggleMaintenance,
  showMaintenancePopup,
  setShowMaintenancePopup,
  // Tabs
  tabs,
  activeTab,
  onTabChange,
  // Visitor preview
  isVisitorPreviewActive,
  onToggleVisitorPreview,
  // Translations
  t
}) => {
  return (
    <>
      {/* Header avec Solde et Stats - Design "Zero Frame" v12.1 */}
      <div className="mb-6">
        {/* Titre et Solde - Sans cadre */}
        <div className="flex justify-between items-start mb-4">
          <div>
            <h1 className="text-xl font-bold text-white" data-testid="dashboard-title">
              {coachPlatformName || (isSuperAdmin ? 'Afroboost HQ' : 'Mon Espace')}
            </h1>
            {coachUser?.email && (
              <p className="text-white/40 text-xs mt-0.5">{coachUser.email}</p>
            )}
          </div>
          
          {/* Solde Crédits - Affiché uniquement pour les partenaires */}
          {!isSuperAdmin && (
            <div 
              className="px-4 py-2 rounded-lg text-right"
              style={{ background: 'transparent' }}
              data-testid="credits-display"
            >
              <div className="text-white/50 text-xs">Crédits</div>
              <div 
                className="text-xl font-bold"
                style={{ color: coachCredits < 5 ? '#ef4444' : '#D91CD2' }}
              >
                {coachCredits === -1 ? '∞' : coachCredits}
              </div>
            </div>
          )}
        </div>
        
        {/* Cartes Stats - Design v12.1 Sans Bordure */}
        <div className="grid grid-cols-4 gap-2 sm:gap-3">
          {/* === CARTE RÉSERVATIONS === */}
          <div 
            className="h-20 rounded-2xl flex flex-col items-center justify-center gap-1"
            style={{ 
              background: 'rgba(255,255,255,0.03)',
              borderBottom: '1px solid rgba(255,255,255,0.05)'
            }}
            data-testid="reservations-stat-card"
          >
            <span className="text-2xl font-bold" style={{ color: '#D91CD2' }}>{totalReservations}</span>
            <span className="text-white/50 text-xs">Réservations</span>
          </div>
          
          {/* === CARTE CONTACTS === */}
          <div 
            className="h-20 rounded-2xl flex flex-col items-center justify-center gap-1"
            style={{ 
              background: 'rgba(255,255,255,0.03)',
              borderBottom: '1px solid rgba(255,255,255,0.05)'
            }}
            data-testid="contacts-stat-card"
          >
            <span className="text-2xl font-bold" style={{ color: '#8b5cf6' }}>{totalContacts}</span>
            <span className="text-white/50 text-xs">Contacts</span>
          </div>
          
          {/* === CARTE ADMIN (Super Admin) ou STRIPE (Coach) === */}
          {isSuperAdmin ? (
            <button 
              onClick={onOpenAdminPanel}
              title="Panneau Super Admin"
              className="h-20 rounded-2xl flex flex-col items-center justify-center gap-2 transition-all duration-200 hover:scale-105"
              style={{ 
                background: 'rgba(255,255,255,0.03)',
                borderBottom: '1px solid rgba(217, 28, 210, 0.2)'
              }}
              data-testid="super-admin-btn"
            >
              <StarIcon />
              <span className="text-white/80 text-xs">Admin</span>
            </button>
          ) : (
            <button 
              onClick={onStripeConnect}
              disabled={stripeConnectLoading}
              title={stripeConnectStatus?.connected ? "Compte Stripe connecté" : "Connecter votre Stripe"}
              className="h-20 rounded-2xl flex flex-col items-center justify-center gap-2 transition-all duration-200 hover:scale-105"
              style={{ 
                background: stripeConnectStatus?.connected 
                  ? 'rgba(34, 197, 94, 0.1)' 
                  : 'rgba(255,255,255,0.03)',
                borderBottom: stripeConnectStatus?.connected 
                  ? '1px solid rgba(34, 197, 94, 0.3)' 
                  : '1px solid rgba(255,255,255,0.05)',
                opacity: stripeConnectLoading ? 0.7 : 1
              }}
              data-testid="stripe-connect-btn"
            >
              <span className="text-lg">{stripeConnectStatus?.connected ? '✅' : '💳'}</span>
              <span className="text-white/80 text-xs">{stripeConnectLoading ? '...' : 'Stripe'}</span>
            </button>
          )}
          
          {/* === CARTE PARTAGER === */}
          <button 
            onClick={onShareLink}
            title={linkCopied ? "Lien copié !" : "Partager le site"}
            className="h-20 rounded-2xl flex flex-col items-center justify-center gap-2 transition-all duration-200 hover:scale-105"
            style={{ 
              background: linkCopied 
                ? 'rgba(34, 197, 94, 0.1)' 
                : 'rgba(255,255,255,0.03)',
              borderBottom: linkCopied 
                ? '1px solid rgba(34, 197, 94, 0.3)' 
                : '1px solid rgba(255,255,255,0.05)'
            }}
            data-testid="coach-share"
          >
            {linkCopied ? <CheckIcon /> : <ShareIcon />}
            <span className="text-white/80 text-xs">{linkCopied ? 'Copié!' : 'Partager'}</span>
          </button>
        </div>
      </div>

      {/* Navigation Onglets - Scrollable horizontalement */}
      <div 
        className="flex gap-2 mb-6 items-center pb-2"
        style={{
          overflowX: 'auto',
          overflowY: 'hidden',
          whiteSpace: 'nowrap',
          WebkitOverflowScrolling: 'touch',
          scrollbarWidth: 'none',
          msOverflowStyle: 'none'
        }}
      >
        {tabs.map(tb => (
          <button 
            key={tb.id} 
            onClick={() => onTabChange(tb.id)} 
            className={`coach-tab px-3 py-2 rounded-lg text-xs sm:text-sm flex-shrink-0 ${activeTab === tb.id ? 'active' : ''}`}
            style={{ color: 'white' }} 
            data-testid={`coach-tab-${tb.id}`}
          >
            {tb.label}
          </button>
        ))}
        
        {/* Bouton Vue Visiteur — V64: RÈGLE D'OR Super Admin = /coach/bassi */}
        <button
          onClick={() => {
            const SUPER_ADMIN_EMAILS = ['contact.artboost@gmail.com', 'afroboost.bassi@gmail.com'];
            const isSA = SUPER_ADMIN_EMAILS.includes(coachUser?.email?.toLowerCase());
            const slug = isSA ? 'bassi' : (coachUser?.username || coachUser?.name?.toLowerCase().split(' ')[0].trim() || 'coach');
            const vitrineUrl = `${window.location.origin}/coach/${slug}?t=${Date.now()}`;
            console.log('[V64] DashboardHeader Vue Visiteur →', vitrineUrl);
            window.open(vitrineUrl, '_blank');
          }}
          className="ml-auto px-3 py-2 rounded-lg text-xs sm:text-sm flex items-center gap-2 flex-shrink-0"
          style={{
            background: 'rgba(255,255,255,0.03)',
            border: 'none',
            borderBottom: '1px solid rgba(255,255,255,0.05)',
            color: 'white'
          }}
          title="Voir ma vitrine publique"
          data-testid="coach-visitor-preview-toggle"
        >
          <ExternalLinkIcon />
          <span className="hidden sm:inline">Vue Visiteur</span>
        </button>
      </div>
    </>
  );
};

export default DashboardHeader;

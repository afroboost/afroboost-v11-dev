/**
 * ReservationTab.js - Composant de présentation pour l'onglet Réservations
 * 
 * Extrait de CoachDashboard.js pour alléger le fichier principal.
 * Ce composant est purement présentatif : toute la logique reste dans CoachDashboard.
 * 
 * Props attendues:
 * - reservations: Liste des réservations filtrées
 * - pagination: Objet {page, pages, total, limit}
 * - search: Terme de recherche
 * - loading: État de chargement
 * - handlers: Objet contenant les fonctions de callback
 * - t: Fonction de traduction
 */

import React, { memo } from 'react';

const ReservationTab = ({
  reservations,
  pagination,
  search,
  loading,
  handlers,
  t
}) => {
  const {
    onSearchChange,
    onClearSearch,
    onScanClick,
    onExportCSV,
    onPageChange,
    onValidateReservation,
    onDeleteReservation,
    formatDateTime
  } = handlers;

  return (
    <div className="card-gradient rounded-xl p-4 sm:p-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-4 gap-4">
        <div>
          <h2 className="font-semibold text-white text-lg sm:text-xl">{t('reservationsList')}</h2>
          <p className="text-white/50 text-xs mt-1">
            {pagination.total > 0 
              ? `Affichage ${((pagination.page - 1) * pagination.limit) + 1}-${Math.min(pagination.page * pagination.limit, pagination.total)} sur ${pagination.total} réservations`
              : 'Aucune réservation'}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button 
            onClick={onScanClick} 
            className="btn-primary px-3 py-2 rounded-lg flex items-center gap-2 text-xs sm:text-sm" 
            data-testid="scan-ticket-btn"
          >
            📷 Scanner
          </button>
          <button 
            onClick={onExportCSV} 
            className="csv-btn text-xs sm:text-sm" 
            data-testid="export-csv"
          >
            {t('downloadCSV')}
          </button>
        </div>
      </div>
      
      {/* Barre de recherche */}
      <div className="mb-4">
        <div className="relative">
          <input
            type="text"
            placeholder="🔍 Rechercher par nom, email, WhatsApp, date, code..."
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full px-4 py-2.5 pl-10 rounded-lg text-sm"
            style={{ background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)', color: '#fff' }}
            data-testid="reservations-search-input"
          />
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-white/50">🔍</span>
          {search && (
            <button
              onClick={onClearSearch}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-white/50 hover:text-white"
            >✕</button>
          )}
        </div>
        {search && (
          <p className="text-xs text-purple-400 mt-1">
            {reservations.length} résultat(s)
          </p>
        )}
      </div>
      
      {/* Pagination */}
      {pagination.pages > 1 && (
        <div className="flex justify-center items-center gap-2 mb-4">
          <button 
            onClick={() => onPageChange(pagination.page - 1)}
            disabled={pagination.page <= 1 || loading}
            className="px-3 py-1 rounded bg-purple-600/50 text-white text-sm disabled:opacity-30 hover:bg-purple-600"
          >
            ← Précédent
          </button>
          <span className="text-white text-sm px-3">
            Page {pagination.page} / {pagination.pages}
          </span>
          <button 
            onClick={() => onPageChange(pagination.page + 1)}
            disabled={pagination.page >= pagination.pages || loading}
            className="px-3 py-1 rounded bg-purple-600/50 text-white text-sm disabled:opacity-30 hover:bg-purple-600"
          >
            Suivant →
          </button>
        </div>
      )}
      
      {/* Loading state */}
      {loading && (
        <div className="text-center py-4 text-purple-400">⏳ Chargement...</div>
      )}
      
      {/* === MOBILE VIEW: Cards === */}
      <div className="block md:hidden space-y-3 max-h-[600px] overflow-y-auto scrollbar-thin pr-2">
        {reservations.map(r => {
          const isProduct = r.selectedVariants || r.trackingNumber || r.shippingStatus !== 'pending';
          return (
            <ReservationCard 
              key={r.id} 
              reservation={r}
              isProduct={isProduct}
              onValidate={() => onValidateReservation(r.id)}
              onDelete={() => onDeleteReservation(r.id)}
              formatDateTime={formatDateTime}
            />
          );
        })}
        {reservations.length === 0 && !loading && (
          <p className="text-white/50 text-center py-8">Aucune réservation</p>
        )}
      </div>
      
      {/* === DESKTOP VIEW: Table === */}
      <div className="hidden md:block overflow-x-auto max-h-[600px] scrollbar-thin">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-[#1a1a2e]">
            <tr className="text-left text-white/60 text-xs">
              <th className="pb-3 font-medium">Code</th>
              <th className="pb-3 font-medium">Client</th>
              <th className="pb-3 font-medium">Contact</th>
              <th className="pb-3 font-medium">Date</th>
              <th className="pb-3 font-medium">Type</th>
              <th className="pb-3 font-medium">Statut</th>
              <th className="pb-3 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/10">
            {reservations.map(r => {
              const isProduct = r.selectedVariants || r.trackingNumber || r.shippingStatus !== 'pending';
              return (
                <ReservationRow 
                  key={r.id}
                  reservation={r}
                  isProduct={isProduct}
                  onValidate={() => onValidateReservation(r.id)}
                  onDelete={() => onDeleteReservation(r.id)}
                  formatDateTime={formatDateTime}
                />
              );
            })}
          </tbody>
        </table>
        {reservations.length === 0 && !loading && (
          <p className="text-white/50 text-center py-8">Aucune réservation</p>
        )}
      </div>
    </div>
  );
};

// === SOUS-COMPOSANTS MÉMOÏSÉS ===

const ReservationCard = memo(({ reservation: r, isProduct, onValidate, onDelete, formatDateTime }) => (
  <div className={`p-4 rounded-lg glass ${r.validated ? 'border border-green-500/30' : 'border border-purple-500/20'}`}>
    <div className="flex justify-between items-start mb-3">
      <div>
        <span className="text-pink-400 font-bold text-sm">{r.reservationCode || '-'}</span>
        <h3 className="text-white font-semibold">{r.userName}</h3>
        <p className="text-white/60 text-xs">{r.userEmail}</p>
        {r.userWhatsapp && (
          <a 
            href={`https://wa.me/${r.userWhatsapp.replace(/[^\d+]/g, '')}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-green-400 text-xs hover:underline"
          >
            📱 {r.userWhatsapp}
          </a>
        )}
      </div>
      <div className="flex items-center gap-2">
        {r.validated ? (
          <span className="px-2 py-1 rounded text-xs bg-green-600 text-white">✅</span>
        ) : (
          <span className="px-2 py-1 rounded text-xs bg-yellow-600 text-white">⏳</span>
        )}
        {isProduct && (
          <span className="px-2 py-1 rounded text-xs bg-blue-600 text-white">🛒</span>
        )}
      </div>
    </div>
    
    <div className="text-white/60 text-xs space-y-1 mb-3">
      <p>📅 {formatDateTime(r.datetime)}</p>
      {r.courseName && <p>📚 {r.courseName}</p>}
      {r.promoCode && (
        <p>🎫 Code: <span className="text-yellow-400 font-medium">{r.promoCode}</span>
          {r.subscriptionId && <span className="text-purple-400 ml-1">(abo lié)</span>}
        </p>
      )}
      {r.subscriptionInfo && (
        <p>🎟️ Séances: <span className="text-green-400 font-medium">{r.subscriptionInfo.remaining}/{r.subscriptionInfo.total}</span> restantes</p>
      )}
      {r.source === 'qr_scan' ? (
        <p>📍 <span className="text-green-400">Check-in QR</span></p>
      ) : r.source && (
        <p>📍 Source: {r.source}</p>
      )}
    </div>
    
    <div className="flex gap-2">
      {!r.validated && (
        <button 
          onClick={onValidate}
          className="flex-1 px-3 py-1.5 rounded text-xs bg-green-600/20 text-green-400 hover:bg-green-600/40"
        >
          ✅ Valider
        </button>
      )}
      <button 
        onClick={onDelete}
        className="px-3 py-1.5 rounded text-xs bg-red-600/20 text-red-400 hover:bg-red-600/40"
      >
        🗑️
      </button>
    </div>
  </div>
));

const ReservationRow = memo(({ reservation: r, isProduct, onValidate, onDelete, formatDateTime }) => (
  <tr className="hover:bg-white/5">
    <td className="py-3 text-pink-400 font-medium">{r.reservationCode || '-'}</td>
    <td className="py-3">
      <div className="text-white font-medium">{r.userName}</div>
      <div className="text-white/50 text-xs">{r.userEmail}</div>
    </td>
    <td className="py-3">
      {r.userWhatsapp ? (
        <a 
          href={`https://wa.me/${r.userWhatsapp.replace(/[^\d+]/g, '')}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-green-400 text-xs hover:underline"
        >
          📱 {r.userWhatsapp}
        </a>
      ) : (
        <span className="text-white/30">-</span>
      )}
    </td>
    <td className="py-3 text-white/60 text-xs">{formatDateTime(r.datetime)}</td>
    <td className="py-3">
      <div className="flex flex-col gap-0.5">
        <div className="flex gap-1">
          {r.courseName && <span className="text-xs text-purple-400">📚</span>}
          {isProduct && <span className="text-xs text-blue-400">🛒</span>}
          {r.promoCode && <span className="text-xs text-yellow-400" title={`Code: ${r.promoCode}`}>🎫</span>}
        </div>
        {r.promoCode && (
          <span className="text-[10px] text-yellow-400/70">{r.promoCode}</span>
        )}
        {r.subscriptionInfo && (
          <span className="text-[10px] text-green-400/70">{r.subscriptionInfo.remaining}/{r.subscriptionInfo.total} séances</span>
        )}
        {r.source === 'qr_scan' && (
          <span className="text-[10px] text-green-400">Check-in QR</span>
        )}
      </div>
    </td>
    <td className="py-3">
      {r.validated ? (
        <span className="px-2 py-1 rounded text-xs bg-green-600/20 text-green-400">Validé</span>
      ) : (
        <span className="px-2 py-1 rounded text-xs bg-yellow-600/20 text-yellow-400">En attente</span>
      )}
    </td>
    <td className="py-3 text-right">
      <div className="flex justify-end gap-2">
        {!r.validated && (
          <button 
            onClick={onValidate}
            className="px-2 py-1 rounded text-xs bg-green-600/20 text-green-400 hover:bg-green-600/40"
          >
            ✅
          </button>
        )}
        <button 
          onClick={onDelete}
          className="px-2 py-1 rounded text-xs bg-red-600/20 text-red-400 hover:bg-red-600/40"
        >
          🗑️
        </button>
      </div>
    </td>
  </tr>
));

export default memo(ReservationTab);

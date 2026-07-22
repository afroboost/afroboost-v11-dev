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
import SvgIcon from '../SvgIcon';

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
    onCycleHeadphone, // V185 F4: cycle 🎧 gris → rouge → vert → gris
    onUpdateTracking, // V226: (reservationId, trackingNumber, shippingStatus) — suivi colis
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
            <SvgIcon name="camera" size={14} /> Scanner
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
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-white/50"><SvgIcon name="search" size={14} /></span>
          {search && (
            <button
              onClick={onClearSearch}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-white/50 hover:text-white"
              aria-label="Effacer la recherche"
            ><SvgIcon name="close" size={14} /></button>
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
            <span className="inline-flex items-center gap-1.5"><SvgIcon name="arrowLeft" size={14} />Précédent</span>
          </button>
          <span className="text-white text-sm px-3">
            Page {pagination.page} / {pagination.pages}
          </span>
          <button 
            onClick={() => onPageChange(pagination.page + 1)}
            disabled={pagination.page >= pagination.pages || loading}
            className="px-3 py-1 rounded bg-purple-600/50 text-white text-sm disabled:opacity-30 hover:bg-purple-600"
          >
            <span className="inline-flex items-center gap-1.5">Suivant<SvgIcon name="arrowRight" size={14} /></span>
          </button>
        </div>
      )}
      
      {/* Loading state */}
      {loading && (
        <div className="text-center py-4 text-purple-400"><span className="inline-flex items-center gap-1.5"><SvgIcon name="loader" size={14} className="animate-spin" />Chargement...</span></div>
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
              onCycleHeadphone={onCycleHeadphone || null} /* V191: brut, prend (reservation, guestIndex) */
              onUpdateTracking={onUpdateTracking || null} /* V226 */
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
                  onCycleHeadphone={onCycleHeadphone || null} /* V191: brut, prend (reservation, guestIndex) */
                  onUpdateTracking={onUpdateTracking || null} /* V226 */
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

// V226: `shippingAddress` existe sous DEUX formes en base, selon l'époque du document.
//  1. Chaîne libre — l'ancien formulaire vitrine (App.js:4886) envoie le contenu brut
//     d'un <input type="text"> ; le modèle backend la déclare `Optional[str]`
//     (server.py:521). C'est aussi la forme écrite par le webhook V226
//     (server.py:4081), qui pré-joint les composants Stripe avec ", ".
//  2. Objet — jamais écrit par le code actuel, mais une adresse Stripe brute
//     (`{name, address: {line1, postal_code, city, country}}`) est la forme naturelle
//     si un import ou un correctif futur en dépose une. On la met à plat plutôt que
//     de laisser React lever « Objects are not valid as a React child », qui
//     casserait tout l'onglet — donc aussi les réservations de cours de la page.
// Une réservation ancienne sans le champ retourne '' et n'affiche rien de cassé.
const formatShippingAddress = (raw) => {
  if (!raw) return '';
  if (typeof raw === 'string') return raw.trim();
  if (typeof raw === 'object') {
    const a = (raw.address && typeof raw.address === 'object') ? raw.address : raw;
    return [
      raw.name, a.line1, a.line2,
      [a.postal_code, a.city].filter(Boolean).join(' '),
      a.state, a.country
    ].filter(v => typeof v === 'string' && v.trim()).join(', ');
  }
  return String(raw);
};

// V226: `variantsText` est déjà calculé côté serveur (webhook) et côté vitrine, mais
// `selectedVariants` diverge : dict `{taille: "M"}` (modèle legacy server.py:519 et
// webhook V226) ou liste de dicts (modèle actif reservation_routes.py:502). Les deux
// sont mises à plat ici, `variantsText` restant prioritaire quand il est présent.
const formatVariants = (r) => {
  if (r.variantsText && typeof r.variantsText === 'string' && r.variantsText.trim()) return r.variantsText.trim();
  const v = r.selectedVariants;
  if (!v || typeof v !== 'object') return '';
  const pairs = (obj) => Object.entries(obj).map(([k, val]) => `${k}: ${val}`).join(', ');
  if (Array.isArray(v)) return v.filter(o => o && typeof o === 'object').map(pairs).filter(Boolean).join(' — ');
  return pairs(v);
};

// V226: signal FIABLE de commande physique, distinct du booléen `isProduct` calculé
// plus haut. `isProduct` vaut vrai dès que `shippingStatus !== 'pending'`, donc aussi
// pour un document ancien où le champ est simplement absent (undefined !== 'pending').
// Monter le bloc d'expédition sur ce booléen ferait apparaître une adresse vide et un
// formulaire de colis sur des réservations de COURS anciennes — la régression exacte à
// éviter. On exige donc une preuve positive d'achat physique. Le badge 🛒 existant
// n'est pas touché : sa condition reste celle d'avant.
const hasShippingData = (r) => !!(
  r.isProduct === true ||
  (typeof r.shippingAddress === 'string' ? r.shippingAddress.trim() : r.shippingAddress) ||
  (r.variantsText && String(r.variantsText).trim()) ||
  r.trackingNumber ||
  (r.selectedVariants && typeof r.selectedVariants === 'object' && Object.keys(r.selectedVariants).length > 0)
);

// V226: bloc expédition — taille/variantes, adresse, et saisie du suivi de colis.
// Rendu UNIQUEMENT quand hasShippingData est vrai : aucun de ces nœuds n'est monté
// pour une réservation de cours, dont l'affichage reste strictement identique.
const ShippingBlock = memo(({ reservation: r, onUpdateTracking }) => {
  const address = formatShippingAddress(r.shippingAddress);
  const variants = formatVariants(r);
  const inputStyle = {
    background: '#0a0a0f', border: '1px solid #333',
    borderRadius: '12px', color: '#FFFFFF'
  };
  return (
    <div className="mt-2 pt-2 border-t border-white/10 space-y-1.5" data-testid="shipping-block">
      {variants && (
        <p className="text-xs" style={{ color: '#F0A8EE' }}><SvgIcon name="ruler" size={14} className="mr-1.5" />{variants}</p>
      )}
      <p className="text-xs whitespace-pre-line" style={{ color: '#AAAAAA' }}>
        <SvgIcon name="mail" size={14} className="mr-1.5" />{address || <span className="italic opacity-60">Adresse non renseignée</span>}
      </p>
      {onUpdateTracking && (
        <div className="flex gap-2 items-center pt-1">
          <input
            type="text"
            placeholder="N° de suivi"
            defaultValue={r.trackingNumber || ''}
            onBlur={(e) => {
              const next = e.target.value.trim();
              if (next !== (r.trackingNumber || '')) {
                onUpdateTracking(r.id, next, r.shippingStatus || 'pending');
              }
            }}
            className="v224-input flex-1 min-w-0 px-2 py-1 text-xs"
            style={inputStyle}
            data-testid="tracking-input"
          />
          <select
            value={r.shippingStatus || 'pending'}
            onChange={(e) => onUpdateTracking(r.id, r.trackingNumber || '', e.target.value)}
            className="v224-input px-2 py-1 text-xs"
            style={inputStyle}
            data-testid="shipping-status-select"
          >
            <option value="pending">📦 À expédier</option>
            <option value="shipped">🚚 Expédié</option>
            <option value="delivered">✅ Livré</option>
          </select>
        </div>
      )}
    </div>
  );
});
ShippingBlock.displayName = 'ShippingBlock';

// V185 F4: Bouton 🎧 Casque cyclique (gris → rouge → vert → gris)
const HeadphoneToggle = memo(({ status, onClick, compact, label }) => {
  const map = {
    taken: { color: '#ef4444', bg: 'rgba(239,68,68,0.18)', stateLabel: 'Casque pris' },
    returned: { color: '#22c55e', bg: 'rgba(34,197,94,0.18)', stateLabel: 'Casque rendu' },
  };
  const meta = map[status] || { color: 'rgba(255,255,255,0.4)', bg: 'rgba(255,255,255,0.06)', stateLabel: 'Pas de casque' };
  return (
    <button
      type="button"
      onClick={onClick}
      title={`🎧 ${meta.stateLabel}${label ? ` — ${label}` : ''} — clic pour changer`}
      data-testid="headphone-toggle"
      className="inline-flex items-center gap-1"
      style={{
        padding: compact ? '4px 6px' : '6px 8px', borderRadius: '8px',
        background: meta.bg, color: meta.color, border: 'none', cursor: 'pointer',
        fontSize: compact ? '12px' : '14px', lineHeight: 1, whiteSpace: 'nowrap'
      }}
    >
      <SvgIcon name="headphones" size={14} />
      {label && <span style={{ fontSize: compact ? '10px' : '11px', fontWeight: 500 }}>{label}</span>}
    </button>
  );
});
HeadphoneToggle.displayName = 'HeadphoneToggle';

// V191: Rangée de casques — 1 bouton pour l'abonné + N boutons pour les accompagnants
const HeadphoneRow = memo(({ reservation, onCycle, compact }) => {
  const r = reservation;
  if (!r || !onCycle) return null;
  const guests = Array.isArray(r.guests) ? r.guests : [];
  const guestHp = Array.isArray(r.guest_headphones) ? r.guest_headphones : [];
  const mainName = (r.userName || '').split(' ')[0] || 'Abonné';
  return (
    <div className="flex flex-wrap gap-1.5 items-center">
      <HeadphoneToggle
        status={r.headphone_status}
        label={mainName}
        compact={compact}
        onClick={() => onCycle(r, null)}
      />
      {guests.map((gname, i) => (
        <HeadphoneToggle
          key={i}
          status={guestHp[i]}
          label={(gname || `Invité ${i + 1}`).split(' ')[0]}
          compact={compact}
          onClick={() => onCycle(r, i)}
        />
      ))}
    </div>
  );
});
HeadphoneRow.displayName = 'HeadphoneRow';

const ReservationCard = memo(({ reservation: r, isProduct, onValidate, onDelete, onCycleHeadphone, onUpdateTracking, formatDateTime }) => (
  <div className={`p-4 rounded-lg glass ${r.validated ? 'border border-green-500/30' : 'border border-purple-500/20'}`}>
    <div className="flex justify-between items-start mb-3">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-pink-400 font-bold text-sm">{r.reservationCode || '-'}</span>
          {/* V191: badge × N places si réservation multi-personnes */}
          {Number(r.quantity) > 1 && (
            <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: 'rgba(217,28,210,0.18)', color: '#F0A8EE' }}>
              × {r.quantity} places
            </span>
          )}
        </div>
        <h3 className="text-white font-semibold">{r.userName}</h3>
        <p className="text-white/60 text-xs">{r.userEmail}</p>
        {/* V191: Liste des accompagnants */}
        {Array.isArray(r.guests) && r.guests.length > 0 && (
          <p className="text-white/70 text-xs mt-1">
            <SvgIcon name="users" size={14} className="mr-1.5" />{[((r.userName || '').split(' ')[0] || 'Abonné'), ...r.guests].join(', ')}
          </p>
        )}
        {r.userWhatsapp && (
          <a
            href={`https://wa.me/${r.userWhatsapp.replace(/[^\d+]/g, '')}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-green-400 text-xs hover:underline"
          >
            <SvgIcon name="phone" size={14} className="mr-1.5" />{r.userWhatsapp}
          </a>
        )}
      </div>
      <div className="flex items-center gap-2">
        {r.validated ? (
          <span className="px-2 py-1 rounded text-xs bg-green-600 text-white" title="Validé"><SvgIcon name="check" size={14} /></span>
        ) : (
          <span className="px-2 py-1 rounded text-xs bg-yellow-600 text-white" title="En attente"><SvgIcon name="hourglass" size={14} /></span>
        )}
        {isProduct && (
          <span className="px-2 py-1 rounded text-xs bg-blue-600 text-white" title="Commande produit"><SvgIcon name="shoppingCart" size={14} /></span>
        )}
      </div>
    </div>
    
    <div className="text-white/60 text-xs space-y-1 mb-3">
      {/* v158.7: Afficher la date de reservation (createdAt) en plus de la date de session */}
      {r.createdAt && (
        <p><SvgIcon name="calendar" size={14} className="mr-1.5" /><span className="text-blue-300">Réservé le :</span> {new Date(r.createdAt).toLocaleString('fr-CH', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}</p>
      )}
      <p><SvgIcon name="calendar" size={14} className="mr-1.5" /><span className="text-purple-300">Session :</span> {formatDateTime(r.datetime)}</p>
      {r.courseName && <p><SvgIcon name="book" size={14} className="mr-1.5" />{r.courseName}</p>}
      {r.promoCode && (
        <p><SvgIcon name="ticket" size={14} className="mr-1.5" />Code: <span className="text-yellow-400 font-medium">{r.promoCode}</span>
          {r.subscriptionId && <span className="text-purple-400 ml-1">(abo lié)</span>}
        </p>
      )}
      {r.subscriptionInfo && (
        <p><SvgIcon name="ticket" size={14} className="mr-1.5" />Séances: <span className="text-green-400 font-medium">{r.subscriptionInfo.remaining}/{r.subscriptionInfo.total}</span> restantes</p>
      )}
      {r.source === 'qr_scan' ? (
        <p><SvgIcon name="mapPin" size={14} className="mr-1.5" /><span className="text-green-400">Check-in QR</span></p>
      ) : r.source && (
        <p><SvgIcon name="mapPin" size={14} className="mr-1.5" />Source: {r.source}</p>
      )}
      {/* V226: où expédier et dans quelle taille — commandes physiques uniquement */}
      {hasShippingData(r) && (
        <ShippingBlock reservation={r} onUpdateTracking={onUpdateTracking} />
      )}
    </div>

    {/* V191: Rangée casques — 1 toggle par personne (abonné + guests) */}
    {onCycleHeadphone && (
      <div className="mb-3">
        <HeadphoneRow reservation={r} onCycle={onCycleHeadphone} />
      </div>
    )}

    <div className="flex gap-2 items-center">
      {!r.validated && (
        <button
          onClick={onValidate}
          className="flex-1 px-3 py-1.5 rounded text-xs bg-green-600/20 text-green-400 hover:bg-green-600/40"
        >
          <span className="inline-flex items-center gap-1.5"><SvgIcon name="check" size={14} />Valider</span>
        </button>
      )}
      <button
        onClick={onDelete}
        className="px-3 py-1.5 rounded text-xs bg-red-600/20 text-red-400 hover:bg-red-600/40"
        aria-label="Supprimer la réservation"
      >
        <SvgIcon name="trash" size={14} />
      </button>
    </div>
  </div>
));

const ReservationRow = memo(({ reservation: r, isProduct, onValidate, onDelete, onCycleHeadphone, onUpdateTracking, formatDateTime }) => (
  <>
  <tr className="hover:bg-white/5">
    <td className="py-3 text-pink-400 font-medium">
      <div>{r.reservationCode || '-'}</div>
      {/* V191: badge × N places */}
      {Number(r.quantity) > 1 && (
        <div className="text-[10px] mt-1 inline-block px-2 py-0.5 rounded-full" style={{ background: 'rgba(217,28,210,0.18)', color: '#F0A8EE' }}>
          × {r.quantity} places
        </div>
      )}
    </td>
    <td className="py-3">
      <div className="text-white font-medium">{r.userName}</div>
      <div className="text-white/50 text-xs">{r.userEmail}</div>
      {/* V191: Liste des accompagnants */}
      {Array.isArray(r.guests) && r.guests.length > 0 && (
        <div className="text-white/60 text-[11px] mt-1">
          <SvgIcon name="users" size={14} className="mr-1.5" />{[((r.userName || '').split(' ')[0] || 'Abonné'), ...r.guests].join(', ')}
        </div>
      )}
      {/* V191: Casques individuels (un toggle par personne) */}
      {onCycleHeadphone && (
        <div className="mt-2">
          <HeadphoneRow reservation={r} onCycle={onCycleHeadphone} compact />
        </div>
      )}
    </td>
    <td className="py-3">
      {r.userWhatsapp ? (
        <a 
          href={`https://wa.me/${r.userWhatsapp.replace(/[^\d+]/g, '')}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-green-400 text-xs hover:underline"
        >
          <SvgIcon name="phone" size={14} className="mr-1.5" />{r.userWhatsapp}
        </a>
      ) : (
        <span className="text-white/30">-</span>
      )}
    </td>
    <td className="py-3 text-white/60 text-xs">
      {/* v158.7: Afficher d'abord la date de reservation, puis la date de session */}
      {r.createdAt && (
        <div className="text-blue-300 text-[10px]">
          <SvgIcon name="calendar" size={14} className="mr-1.5" />Réservé: {new Date(r.createdAt).toLocaleDateString('fr-CH', { day: '2-digit', month: '2-digit', year: '2-digit' })}
        </div>
      )}
      <div className="text-purple-300"><SvgIcon name="calendar" size={14} className="mr-1.5" />{formatDateTime(r.datetime)}</div>
    </td>
    <td className="py-3">
      <div className="flex flex-col gap-0.5">
        <div className="flex gap-1">
          {r.courseName && <span className="text-xs text-purple-400" title="Cours"><SvgIcon name="book" size={14} /></span>}
          {isProduct && <span className="text-xs text-blue-400" title="Commande produit"><SvgIcon name="shoppingCart" size={14} /></span>}
          {r.promoCode && <span className="text-xs text-yellow-400" title={`Code: ${r.promoCode}`}><SvgIcon name="ticket" size={14} /></span>}
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
      {/* V191: les casques sont maintenant dans la colonne Client (un par personne) */}
      <div className="flex justify-end gap-2 items-center">
        {!r.validated && (
          <button
            onClick={onValidate}
            className="px-2 py-1 rounded text-xs bg-green-600/20 text-green-400 hover:bg-green-600/40"
            aria-label="Valider la réservation"
          >
            <SvgIcon name="check" size={14} />
          </button>
        )}
        <button
          onClick={onDelete}
          className="px-2 py-1 rounded text-xs bg-red-600/20 text-red-400 hover:bg-red-600/40"
          aria-label="Supprimer la réservation"
        >
          <SvgIcon name="trash" size={14} />
        </button>
      </div>
    </td>
  </tr>
  {/* V226: seconde ligne d'expédition, montée uniquement pour une commande
      physique. Une réservation de cours ne rend que le <tr> ci-dessus, à
      l'identique de l'existant — aucune cellule ni ligne vide n'est ajoutée. */}
  {hasShippingData(r) && (
    <tr className="hover:bg-white/5">
      <td colSpan={7} className="pb-3 pt-0">
        <ShippingBlock reservation={r} onUpdateTracking={onUpdateTracking} />
      </td>
    </tr>
  )}
  </>
));

export default memo(ReservationTab);

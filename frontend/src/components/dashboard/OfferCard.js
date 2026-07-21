// V224 — Carte d'offre pour le dashboard coach.
import React from 'react';

const PINK = '#D91CD2';

export default function OfferCard({ offer, onEdit, onDuplicate, onDelete, onToggleVisible }) {
  const cover = (offer.images || []).find(Boolean) || offer.thumbnail || '';
  const isVisible = offer.visible !== false;

  return (
    <div
      className="transition-all"
      style={{
        background: '#1a1a2e',
        border: '1px solid rgba(217,28,210,0.2)',
        borderRadius: '12px',
        overflow: 'hidden'
      }}
    >
      {cover ? (
        <img src={cover} alt={offer.name} style={{ width: '100%', aspectRatio: '16 / 9', objectFit: 'cover' }} />
      ) : (
        <div style={{ width: '100%', aspectRatio: '16 / 9', background: '#0a0a0f', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '32px' }}>🎧</div>
      )}

      <div style={{ padding: '14px' }}>
        <h3 className="text-white font-semibold text-sm mb-2">{offer.name}</h3>

        <div className="flex items-center gap-2 mb-2">
          <span
            className="text-xs px-2 py-0.5 rounded-full"
            style={{
              background: isVisible ? 'rgba(34,197,94,0.15)' : 'rgba(120,120,120,0.15)',
              color: isVisible ? '#22c55e' : '#888'
            }}
          >
            {isVisible ? 'Active' : 'Masquee'}
          </span>
          <button type="button" onClick={() => onToggleVisible(offer)} className="text-xs" style={{ color: PINK }}>
            {isVisible ? 'Masquer' : 'Activer'}
          </button>
        </div>

        {offer.description && (
          <p className="text-xs mb-2" style={{ color: '#aaa' }}>
            {offer.description.length > 110 ? offer.description.slice(0, 110) + '…' : offer.description}
          </p>
        )}

        {/* V224: chaque ligne meta se masque si sa donnee est absente */}
        <p className="text-xs" style={{ color: '#ccc' }}>
          {[offer.name, `${offer.price} CHF`, offer.duration_minutes ? `${offer.duration_minutes} min` : null]
            .filter(Boolean).join(' · ')}
        </p>
        {offer.location && <p className="text-xs mt-1" style={{ color: '#ccc' }}>📍 {offer.location}</p>}
        {offer.max_participants != null && (
          <p className="text-xs mt-1" style={{ color: '#ccc' }}>👥 0/{offer.max_participants} participants</p>
        )}

        <div className="flex gap-2 mt-3">
          <button type="button" onClick={() => onEdit(offer)} className="flex-1 text-xs py-2 rounded-lg" style={{ background: PINK, color: '#fff' }}>✏️ Modifier</button>
          <button type="button" onClick={() => onDuplicate(offer)} className="text-xs py-2 px-3 rounded-lg" style={{ background: '#0a0a0f', border: '1px solid #333', color: '#fff' }}>📋</button>
          <button type="button" onClick={() => onDelete(offer.id)} className="text-xs py-2 px-3 rounded-lg" style={{ background: '#0a0a0f', border: '1px solid #333', color: '#ef4444' }}>🗑️</button>
        </div>
      </div>
    </div>
  );
}

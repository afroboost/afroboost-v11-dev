// V224 — Carte d'offre pour le dashboard coach.
import React from 'react';

const PINK = '#D91CD2';

export default function OfferCard({
  offer,
  onEdit,
  onDuplicate,
  onDelete,
  onToggleVisible,
  // V224: props OPTIONNELLES et non cassantes.
  // canDelete absent => true (comportement anterieur inchange).
  canDelete = true,
  // V224: reorganisation. Les boutons n'apparaissent que si le parent fournit
  // les callbacks (masques par exemple quand une recherche filtre la grille).
  onMoveUp,
  onMoveDown,
  canMoveUp = false,
  canMoveDown = false
}) {
  const cover = (offer.images || []).find(Boolean) || offer.thumbnail || '';
  const isVisible = offer.visible !== false;
  // V224: garde coherente avec les autres lignes meta (on n'affiche rien plutot
  // que « undefined CHF » quand le champ est absent).
  const hasPrice = offer.price !== null && offer.price !== undefined && offer.price !== '';

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
          {/* V224: affordance « offre protegee » reprise de l'ancien rendu en liste */}
          {!canDelete && (
            <span
              className="text-xs px-2 py-0.5 rounded-full"
              style={{ background: 'rgba(120,120,120,0.15)', color: '#888' }}
              title="Vous ne pouvez supprimer que vos propres offres"
            >
              🔒 Protégée
            </span>
          )}
        </div>

        {offer.description && (
          <p className="text-xs mb-2" style={{ color: '#aaa' }}>
            {offer.description.length > 110 ? offer.description.slice(0, 110) + '…' : offer.description}
          </p>
        )}

        {/* V224: chaque ligne meta se masque si sa donnee est absente */}
        <p className="text-xs" style={{ color: '#ccc' }}>
          {/* V224: le nom n'est plus repete ici, il est deja affiche en titre */}
          {[hasPrice ? `${offer.price} CHF` : null, offer.duration_minutes ? `${offer.duration_minutes} min` : null]
            .filter(Boolean).join(' · ')}
        </p>
        {offer.location && <p className="text-xs mt-1" style={{ color: '#ccc' }}>📍 {offer.location}</p>}
        {/* V224 (revue finale): capacite, et non compteur. Le rendu precedent
            ecrivait un « 0/ » en dur — il n'existe aucun champ participants_count
            cote backend pour l'alimenter. Cohérent avec la carte publique
            (App.js). Le comptage reel des inscrits est un chantier separe. */}
        {offer.max_participants != null && (
          <p className="text-xs mt-1" style={{ color: '#ccc' }}>👥 {offer.max_participants} places</p>
        )}

        <div className="flex gap-2 mt-3">
          <button type="button" onClick={() => onEdit(offer)} className="flex-1 text-xs py-2 rounded-lg" style={{ background: PINK, color: '#fff' }}>✏️ Modifier</button>
          <button type="button" onClick={() => onDuplicate(offer)} className="text-xs py-2 px-3 rounded-lg" style={{ background: '#0a0a0f', border: '1px solid #333', color: '#fff' }}>📋</button>
          {/* V224: bouton Supprimer estompe et desactive pour une offre d'un autre coach */}
          <button
            type="button"
            onClick={() => onDelete(offer.id)}
            disabled={!canDelete}
            title={canDelete ? 'Supprimer' : 'Vous ne pouvez supprimer que vos propres offres'}
            className="text-xs py-2 px-3 rounded-lg"
            style={{
              background: '#0a0a0f',
              border: '1px solid #333',
              color: canDelete ? '#ef4444' : '#666',
              opacity: canDelete ? 1 : 0.4,
              cursor: canDelete ? 'pointer' : 'not-allowed'
            }}
          >
            {canDelete ? '🗑️' : '🔒'}
          </button>
        </div>

        {/* V224: reorganisation de l'ordre d'affichage (champ `position`) */}
        {(onMoveUp || onMoveDown) && (
          <div className="flex items-center gap-2 mt-2">
            <span className="text-xs" style={{ color: '#777' }}>Ordre</span>
            <button
              type="button"
              onClick={() => onMoveUp && onMoveUp(offer)}
              disabled={!canMoveUp}
              title="Monter cette offre"
              className="text-xs py-1 px-2 rounded-lg"
              style={{
                background: '#0a0a0f',
                border: '1px solid rgba(217,28,210,0.2)',
                color: '#fff',
                opacity: canMoveUp ? 1 : 0.3,
                cursor: canMoveUp ? 'pointer' : 'not-allowed'
              }}
            >▲</button>
            <button
              type="button"
              onClick={() => onMoveDown && onMoveDown(offer)}
              disabled={!canMoveDown}
              title="Descendre cette offre"
              className="text-xs py-1 px-2 rounded-lg"
              style={{
                background: '#0a0a0f',
                border: '1px solid rgba(217,28,210,0.2)',
                color: '#fff',
                opacity: canMoveDown ? 1 : 0.3,
                cursor: canMoveDown ? 'pointer' : 'not-allowed'
              }}
            >▼</button>
          </div>
        )}
      </div>
    </div>
  );
}

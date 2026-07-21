// V224 — Carte d'offre pour le dashboard coach.
import React from 'react';

const PINK = '#D91CD2';

// V226: icones SVG extraites en petits composants locaux (a la place des
// emoji ⏱/📍/👥) — memes traces que la carte publique (App.js), reutilisees
// a plusieurs endroits de cette carte plutot que recopiees inline. `color`
// est parametrable (gris #aaa par defaut, valeur de marque possible pour un
// usage cliquable ailleurs) ; `ClockIcon` n'est pas encore consommee dans
// cette carte (la duree n'y est pour l'instant qu'affichee en texte) mais
// fait partie du meme jeu d'icones que le pin et les personnes.
const ICON_PROPS = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round' };

function ClockIcon({ color = '#aaa' }) {
  return (
    <svg {...ICON_PROPS} stroke={color}>
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

function PinIcon({ color = '#aaa' }) {
  return (
    <svg {...ICON_PROPS} stroke={color}>
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  );
}

function PeopleIcon({ color = '#aaa' }) {
  return (
    <svg {...ICON_PROPS} stroke={color}>
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

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
  canMoveDown = false,
  // V226: glisser-deposer. Props OPTIONNELLES : un montage qui ne les passe pas
  // obtient exactement la carte d'avant (draggable=false, aucun handler, curseur
  // par defaut, bordure et opacite inchangees).
  draggable = false,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
  isDragging = false,
  isDragOver = false
}) {
  const cover = (offer.images || []).find(Boolean) || offer.thumbnail || '';
  const isVisible = offer.visible !== false;
  // V224: garde coherente avec les autres lignes meta (on n'affiche rien plutot
  // que « undefined CHF » quand le champ est absent).
  const hasPrice = offer.price !== null && offer.price !== undefined && offer.price !== '';

  return (
    <div
      className="transition-all"
      // V226: la carte n'est glissable que si le parent l'autorise explicitement.
      draggable={draggable}
      data-offer-id={offer.id}
      onDragStart={draggable && onDragStart ? (e) => onDragStart(e, offer) : undefined}
      // V226: onDragOver/onDrop restent actifs meme sur une carte non glissable :
      // une carte doit pouvoir servir de CIBLE de depot sans etre elle-meme
      // deplacable (offre d'un autre coach, par exemple).
      onDragOver={onDragOver ? (e) => onDragOver(e, offer) : undefined}
      onDrop={onDrop ? (e) => onDrop(e, offer) : undefined}
      onDragEnd={onDragEnd ? (e) => onDragEnd(e, offer) : undefined}
      style={{
        background: '#1a1a2e',
        // V226: retour visuel sur la cible survolee. La largeur reste a 1px et
        // le halo est un box-shadow : aucun decalage de mise en page au survol.
        border: `1px solid ${isDragOver ? PINK : 'rgba(217,28,210,0.2)'}`,
        boxShadow: isDragOver ? `0 0 0 2px rgba(217,28,210,0.45)` : 'none',
        borderRadius: '12px',
        overflow: 'hidden',
        // V226: grab au repos, grabbing pendant le deplacement.
        cursor: draggable ? (isDragging ? 'grabbing' : 'grab') : 'default',
        opacity: isDragging ? 0.5 : 1
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
        {/* V226: 📍 remplace par PinIcon — meme condition de masquage inchangee. */}
        {offer.location && (
          <p className="text-xs mt-1 flex items-center gap-1" style={{ color: '#ccc' }}>
            <PinIcon />
            {offer.location}
          </p>
        )}
        {/* V224 (revue finale): capacite, et non compteur. Le rendu precedent
            ecrivait un « 0/ » en dur — il n'existe aucun champ participants_count
            cote backend pour l'alimenter. Cohérent avec la carte publique
            (App.js). Le comptage reel des inscrits est un chantier separe. */}
        {/* V226: 👥 remplace par PeopleIcon — `!= null` (et non la veracite)
            conserve : un 0 est une valeur legitime. */}
        {offer.max_participants != null && (
          <p className="text-xs mt-1 flex items-center gap-1" style={{ color: '#ccc' }}>
            <PeopleIcon />
            {offer.max_participants} places
          </p>
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

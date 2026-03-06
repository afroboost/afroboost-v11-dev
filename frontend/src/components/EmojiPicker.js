// /components/EmojiPicker.js - Sélecteur d'emojis personnalisés pour Coach Bassi
// Extrait de ChatWidget.js pour une meilleure maintenabilité

import { useState, useEffect } from 'react';
import axios from 'axios';

const API = (process.env.REACT_APP_BACKEND_URL || '') + '/api';

/**
 * Parse les tags [emoji:filename.svg] et les convertit en balises <img>
 * Compatible avec linkifyText (préserve les URLs)
 * @param {string} text - Texte avec potentiels tags emoji
 * @returns {string} - Texte avec balises img pour les emojis
 */
export const parseEmojis = (text) => {
  if (!text) return '';
  
  // Regex pour détecter [emoji:filename.svg] ou [emoji:filename]
  const emojiRegex = /\[emoji:([^\]]+)\]/g;
  
  return text.replace(emojiRegex, (match, filename) => {
    // Ajouter .svg si pas d'extension
    const file = filename.includes('.') ? filename : `${filename}.svg`;
    return `<img src="${API}/emojis/${file}" alt="${filename.replace('.svg', '')}" class="chat-emoji" style="width:20px;height:20px;vertical-align:middle;display:inline-block;margin:0 2px;" />`;
  });
};

/**
 * Composant Sélecteur d'Emojis
 * Affiche une grille d'emojis personnalisés
 */
const EmojiPicker = ({ 
  isOpen, 
  onClose, 
  onSelect,
  position = 'bottom' // 'bottom' | 'top'
}) => {
  const [emojis, setEmojis] = useState([]);
  const [loading, setLoading] = useState(true);

  // Charger les emojis depuis l'API
  useEffect(() => {
    const loadEmojis = async () => {
      try {
        const res = await axios.get(`${API}/custom-emojis/list`);
        const emojiList = res.data.emojis || [];
        setEmojis(emojiList.length > 0 ? emojiList : getDefaultEmojis());
      } catch (err) {
        console.warn('[EMOJI] Erreur chargement, utilisation fallback:', err);
        setEmojis(getDefaultEmojis());
      } finally {
        setLoading(false);
      }
    };

    if (isOpen) {
      loadEmojis();
    }
  }, [isOpen]);

  // Emojis par défaut si l'API échoue
  const getDefaultEmojis = () => [
    { name: 'fire', url: '/emojis/fire.svg', filename: 'fire.svg' },
    { name: 'muscle', url: '/emojis/muscle.svg', filename: 'muscle.svg' },
    { name: 'heart', url: '/emojis/heart.svg', filename: 'heart.svg' },
    { name: 'thumbsup', url: '/emojis/thumbsup.svg', filename: 'thumbsup.svg' },
    { name: 'star', url: '/emojis/star.svg', filename: 'star.svg' },
    { name: 'celebration', url: '/emojis/celebration.svg', filename: 'celebration.svg' }
  ];

  const handleSelect = (emoji) => {
    const filename = typeof emoji === 'object' ? emoji.filename : emoji;
    onSelect(filename);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'absolute',
        [position === 'bottom' ? 'bottom' : 'top']: position === 'bottom' ? '60px' : 'auto',
        left: '12px',
        background: 'linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%)',
        border: '1px solid rgba(147, 51, 234, 0.3)',
        borderRadius: '16px',
        padding: '12px',
        zIndex: 1000,
        boxShadow: '0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px rgba(147, 51, 234, 0.1)',
        minWidth: '200px'
      }}
      data-testid="emoji-picker"
    >
      {/* Header */}
      <div style={{ 
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '10px',
        paddingBottom: '8px',
        borderBottom: '1px solid rgba(255,255,255,0.1)'
      }}>
        <span style={{ 
          fontSize: '12px', 
          color: '#a78bfa',
          fontWeight: '600',
          letterSpacing: '0.5px'
        }}>
          💪 Emojis Coach
        </span>
        <button 
          onClick={onClose}
          style={{ 
            background: 'rgba(255,255,255,0.1)', 
            border: 'none', 
            color: '#fff', 
            cursor: 'pointer',
            width: '24px',
            height: '24px',
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '12px',
            transition: 'background 0.2s'
          }}
          onMouseOver={(e) => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.3)'}
          onMouseOut={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'}
          data-testid="emoji-picker-close"
        >
          ✕
        </button>
      </div>

      {/* Grille d'emojis */}
      {loading ? (
        <div style={{ 
          color: 'rgba(255,255,255,0.5)', 
          textAlign: 'center',
          padding: '20px',
          fontSize: '12px'
        }}>
          Chargement...
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '6px'
        }}>
          {emojis.map((emoji, idx) => {
            const emojiName = typeof emoji === 'object' ? emoji.name : emoji.replace('.svg', '');
            const emojiUrl = typeof emoji === 'object' ? emoji.url : `/emojis/${emoji}`;
            
            return (
              <button
                key={idx}
                onClick={() => handleSelect(emoji)}
                style={{
                  width: '44px',
                  height: '44px',
                  borderRadius: '10px',
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  transition: 'all 0.2s ease'
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.background = 'rgba(147, 51, 234, 0.3)';
                  e.currentTarget.style.transform = 'scale(1.1)';
                  e.currentTarget.style.borderColor = 'rgba(147, 51, 234, 0.5)';
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
                  e.currentTarget.style.transform = 'scale(1)';
                  e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)';
                }}
                title={emojiName}
                data-testid={`emoji-${emojiName}`}
              >
                <img 
                  src={`${API}${emojiUrl}`} 
                  alt={emojiName}
                  style={{ 
                    width: '26px', 
                    height: '26px',
                    filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.3))'
                  }}
                  onError={(e) => { 
                    // Fallback: afficher le nom si l'image ne charge pas
                    e.target.style.display = 'none';
                    e.target.parentElement.textContent = emojiName.charAt(0).toUpperCase();
                  }}
                />
              </button>
            );
          })}
        </div>
      )}

      {/* Footer avec raccourcis emoji natifs */}
      <div style={{
        marginTop: '10px',
        paddingTop: '8px',
        borderTop: '1px solid rgba(255,255,255,0.1)',
        display: 'flex',
        justifyContent: 'center',
        gap: '8px'
      }}>
        {['🔥', '💪', '❤️', '👍', '⭐', '🎉'].map((emoji, idx) => (
          <button
            key={idx}
            onClick={() => onSelect(emoji)}
            style={{
              background: 'none',
              border: 'none',
              fontSize: '18px',
              cursor: 'pointer',
              padding: '4px',
              borderRadius: '4px',
              transition: 'transform 0.1s'
            }}
            onMouseOver={(e) => e.currentTarget.style.transform = 'scale(1.3)'}
            onMouseOut={(e) => e.currentTarget.style.transform = 'scale(1)'}
            title="Emoji rapide"
          >
            {emoji}
          </button>
        ))}
      </div>
    </div>
  );
};

export default EmojiPicker;

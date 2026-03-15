// AfricanEmojiPicker.js — African-themed emoji picker component
// Dark theme (#1a1a2e) with cultural emojis and expressions
// Categories: Expressions, Danses & Musique, Sport & Énergie, Coeur & Amour, Afrique, Réactions

import React, { useState, memo } from 'react';
import { X } from 'lucide-react';

const EMOJI_CATEGORIES = {
  expressions: {
    label: 'Expressions',
    emojis: ['😊', '😄', '😂', '🤣', '😍', '🥰', '😘', '😎', '🤩', '😇', '🙏🏿', '👏🏿', '💪🏿', '🤝🏿', '👊🏿', '✊🏿', '🤟🏿', '👋🏿', '🙌🏿', '💃🏿'],
  },
  dances: {
    label: 'Danses & Musique',
    emojis: ['💃🏿', '🕺🏿', '🎶', '🎵', '🥁', '🎺', '🎧', '🎤', '🎼', '🪘', '🎉', '🎊', '🪩', '🎭', '🎪'],
  },
  sport: {
    label: 'Sport & Énergie',
    emojis: ['🏋🏿', '🏃🏿‍♂️', '🏃🏿‍♀️', '💪🏿', '🔥', '⚡', '💥', '🏆', '🥇', '🎯', '💫', '✨', '🌟', '⭐', '🚀'],
  },
  love: {
    label: 'Coeur & Amour',
    emojis: ['❤️', '🧡', '💛', '💚', '💜', '🖤', '💗', '💖', '💝', '💞', '🫶🏿', '💕', '💓', '🤎', '♥️'],
  },
  africa: {
    label: 'Afrique',
    emojis: ['🌍', '🦁', '🐘', '🦒', '🦓', '🌴', '🌺', '🥭', '🍌', '🥥', '☀️', '🌅', '🏔️', '🛖', '🧺'],
  },
  reactions: {
    label: 'Réactions',
    emojis: ['👍🏿', '👎🏿', '👀', '😮', '🫣', '😤', '😢', '🥺', '🤔', '😏', '🙄', '💯', '‼️', '❓', '🆗'],
  },
};

const EmojiButton = memo(({ emoji, onSelect }) => (
  <button
    onClick={() => onSelect(emoji)}
    style={{
      border: 'none',
      background: 'transparent',
      cursor: 'pointer',
      fontSize: '24px',
      padding: '8px',
      borderRadius: '6px',
      transition: 'all 0.2s ease',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: '40px',
      height: '40px',
    }}
    onMouseEnter={(e) => {
      e.target.style.background = 'rgba(217, 28, 210, 0.2)';
      e.target.style.transform = 'scale(1.15)';
    }}
    onMouseLeave={(e) => {
      e.target.style.background = 'transparent';
      e.target.style.transform = 'scale(1)';
    }}
  >
    {emoji}
  </button>
));
EmojiButton.displayName = 'EmojiButton';

const CategoryTab = memo(({ label, isActive, onClick }) => (
  <button
    onClick={onClick}
    style={{
      border: 'none',
      background: isActive ? '#D91CD2' : 'rgba(255,255,255,0.05)',
      color: '#fff',
      padding: '8px 16px',
      borderRadius: '6px',
      cursor: 'pointer',
      fontSize: '13px',
      fontWeight: isActive ? '600' : '500',
      transition: 'all 0.2s ease',
      whiteSpace: 'nowrap',
    }}
    onMouseEnter={(e) => {
      if (!isActive) {
        e.target.style.background = 'rgba(255,255,255,0.1)';
      }
    }}
    onMouseLeave={(e) => {
      if (!isActive) {
        e.target.style.background = 'rgba(255,255,255,0.05)';
      }
    }}
  >
    {label}
  </button>
));
CategoryTab.displayName = 'CategoryTab';

const AfricanEmojiPicker = memo(({ isOpen, onSelect, onClose }) => {
  const [activeCategory, setActiveCategory] = useState('expressions');

  if (!isOpen) return null;

  const handleSelectEmoji = (emoji) => {
    if (onSelect) {
      onSelect(emoji);
    }
    if (onClose) {
      onClose();
    }
  };

  const currentEmojis = EMOJI_CATEGORIES[activeCategory]?.emojis || [];

  return (
    <div
      style={{
        position: 'fixed',
        bottom: '80px',
        right: '16px',
        zIndex: 9999,
        background: '#1a1a2e',
        border: '1px solid rgba(217, 28, 210, 0.2)',
        borderRadius: '12px',
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
        backdropFilter: 'blur(8px)',
        padding: '12px',
        width: '280px',
        maxHeight: '400px',
        display: 'flex',
        flexDirection: 'column',
        animation: 'slideUp 0.2s ease',
      }}
    >
      {/* Header with close button */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '12px',
          paddingBottom: '8px',
          borderBottom: '1px solid rgba(255,255,255,0.1)',
        }}
      >
        <span
          style={{
            color: '#fff',
            fontSize: '13px',
            fontWeight: '600',
          }}
        >
          Émojis Africains
        </span>
        <button
          onClick={onClose}
          style={{
            background: 'rgba(255,255,255,0.05)',
            border: 'none',
            borderRadius: '50%',
            width: '28px',
            height: '28px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            color: '#fff',
            transition: 'all 0.2s ease',
          }}
          onMouseEnter={(e) => {
            e.target.style.background = 'rgba(217, 28, 210, 0.3)';
          }}
          onMouseLeave={(e) => {
            e.target.style.background = 'rgba(255,255,255,0.05)';
          }}
        >
          <X size={16} />
        </button>
      </div>

      {/* Category Tabs */}
      <div
        style={{
          display: 'flex',
          gap: '6px',
          marginBottom: '12px',
          overflowX: 'auto',
          paddingBottom: '4px',
          scrollBehavior: 'smooth',
        }}
      >
        {Object.entries(EMOJI_CATEGORIES).map(([key, category]) => (
          <CategoryTab
            key={key}
            label={category.label}
            isActive={activeCategory === key}
            onClick={() => setActiveCategory(key)}
          />
        ))}
      </div>

      {/* Emoji Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(5, 1fr)',
          gap: '4px',
          overflowY: 'auto',
          overflowX: 'hidden',
          maxHeight: '300px',
          padding: '4px',
        }}
      >
        {currentEmojis.map((emoji, index) => (
          <EmojiButton
            key={`${activeCategory}-${index}`}
            emoji={emoji}
            onSelect={handleSelectEmoji}
          />
        ))}
      </div>

      {/* Add CSS animation via style tag if needed */}
      <style>{`
        @keyframes slideUp {
          from {
            opacity: 0;
            transform: translateY(10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  );
});

AfricanEmojiPicker.displayName = 'AfricanEmojiPicker';

export default AfricanEmojiPicker;

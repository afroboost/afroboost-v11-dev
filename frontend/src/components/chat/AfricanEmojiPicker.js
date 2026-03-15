// AfricanEmojiPicker.js — V143: African-themed emoji picker with Swahili greetings
// Dark theme (#1a1a2e) with cultural emojis, expressions, and Swahili phrases
// Categories use emoji icons in tabs (not text labels)

import React, { useState, memo } from 'react';
import { X } from 'lucide-react';

const EMOJI_CATEGORIES = {
  expressions: {
    icon: '😊',
    label: 'Expressions',
    emojis: ['😊', '😄', '😂', '🤣', '😍', '🥰', '😘', '😎', '🤩', '😇', '🙏🏿', '👏🏿', '💪🏿', '🤝🏿', '👊🏿', '✊🏿', '🤟🏿', '👋🏿', '🙌🏿', '💃🏿'],
  },
  swahili: {
    icon: '🗣️',
    label: 'Swahili',
    emojis: [
      { text: 'Jambo!', desc: 'Bonjour' },
      { text: 'Habari?', desc: 'Comment ça va?' },
      { text: 'Asante', desc: 'Merci' },
      { text: 'Karibu', desc: 'Bienvenue' },
      { text: 'Pole pole', desc: 'Doucement' },
      { text: 'Hakuna Matata', desc: 'Pas de souci' },
      { text: 'Sawa sawa', desc: "D'accord" },
      { text: 'Mambo!', desc: 'Salut!' },
      { text: 'Harambee!', desc: 'Ensemble!' },
      { text: 'Ujamaa', desc: 'Solidarité' },
      { text: 'Umoja', desc: 'Unité' },
      { text: 'Tutaonana', desc: 'À bientôt' },
      { text: 'Rafiki', desc: 'Ami(e)' },
      { text: 'Amani', desc: 'Paix' },
      { text: 'Upendo', desc: 'Amour' },
      { text: 'Kwaheri', desc: 'Au revoir' },
      { text: 'Ndiyo!', desc: 'Oui!' },
      { text: 'Tuko pamoja', desc: 'On est ensemble' },
      { text: 'Maisha', desc: 'La vie' },
      { text: 'Nguvu', desc: 'Force' },
    ],
  },
  dances: {
    icon: '🥁',
    label: 'Musique',
    emojis: ['💃🏿', '🕺🏿', '🎶', '🎵', '🥁', '🎺', '🎧', '🎤', '🎼', '🪘', '🎉', '🎊', '🪩', '🎭', '🎪'],
  },
  sport: {
    icon: '💪🏿',
    label: 'Énergie',
    emojis: ['🏋🏿', '🏃🏿‍♂️', '🏃🏿‍♀️', '💪🏿', '🔥', '⚡', '💥', '🏆', '🥇', '🎯', '💫', '✨', '🌟', '⭐', '🚀'],
  },
  love: {
    icon: '❤️',
    label: 'Amour',
    emojis: ['❤️', '🧡', '💛', '💚', '💜', '🖤', '💗', '💖', '💝', '💞', '🫶🏿', '💕', '💓', '🤎', '♥️'],
  },
  africa: {
    icon: '🌍',
    label: 'Afrique',
    emojis: ['🌍', '🦁', '🐘', '🦒', '🦓', '🌴', '🌺', '🥭', '🍌', '🥥', '☀️', '🌅', '🏔️', '🛖', '🧺'],
  },
  reactions: {
    icon: '👍🏿',
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
      e.currentTarget.style.background = 'rgba(217, 28, 210, 0.2)';
      e.currentTarget.style.transform = 'scale(1.15)';
    }}
    onMouseLeave={(e) => {
      e.currentTarget.style.background = 'transparent';
      e.currentTarget.style.transform = 'scale(1)';
    }}
  >
    {emoji}
  </button>
));
EmojiButton.displayName = 'EmojiButton';

// Swahili phrase button - wider, shows text + translation
const SwahiliButton = memo(({ phrase, onSelect }) => (
  <button
    onClick={() => onSelect(phrase.text)}
    style={{
      border: '1px solid rgba(217, 28, 210, 0.15)',
      background: 'rgba(217, 28, 210, 0.06)',
      cursor: 'pointer',
      padding: '8px 12px',
      borderRadius: '10px',
      transition: 'all 0.2s ease',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'flex-start',
      gap: '2px',
      width: '100%',
    }}
    onMouseEnter={(e) => {
      e.currentTarget.style.background = 'rgba(217, 28, 210, 0.15)';
      e.currentTarget.style.borderColor = 'rgba(217, 28, 210, 0.4)';
      e.currentTarget.style.transform = 'scale(1.02)';
    }}
    onMouseLeave={(e) => {
      e.currentTarget.style.background = 'rgba(217, 28, 210, 0.06)';
      e.currentTarget.style.borderColor = 'rgba(217, 28, 210, 0.15)';
      e.currentTarget.style.transform = 'scale(1)';
    }}
  >
    <span style={{ color: '#fff', fontSize: '14px', fontWeight: '600' }}>{phrase.text}</span>
    <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '10px' }}>{phrase.desc}</span>
  </button>
));
SwahiliButton.displayName = 'SwahiliButton';

const CategoryTab = memo(({ icon, label, isActive, onClick }) => (
  <button
    onClick={onClick}
    title={label}
    style={{
      border: 'none',
      background: isActive ? '#D91CD2' : 'rgba(255,255,255,0.05)',
      color: '#fff',
      padding: '6px 10px',
      borderRadius: '8px',
      cursor: 'pointer',
      fontSize: '18px',
      transition: 'all 0.2s ease',
      whiteSpace: 'nowrap',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      minWidth: '36px',
      height: '36px',
    }}
    onMouseEnter={(e) => {
      if (!isActive) {
        e.currentTarget.style.background = 'rgba(255,255,255,0.1)';
      }
    }}
    onMouseLeave={(e) => {
      if (!isActive) {
        e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
      }
    }}
  >
    {icon}
  </button>
));
CategoryTab.displayName = 'CategoryTab';

const AfricanEmojiPicker = memo(({ isOpen, onSelect, onClose, position, customEmojis = [] }) => {
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

  const currentCategory = EMOJI_CATEGORIES[activeCategory];
  const isSwahili = activeCategory === 'swahili';
  const isCoachCustom = activeCategory === 'coach_custom';

  // Determine position style based on context (dashboard vs widget)
  const posStyle = position === 'above-input'
    ? { position: 'absolute', bottom: '100%', left: '0', marginBottom: '8px' }
    : { position: 'fixed', bottom: '80px', right: '16px' };

  return (
    <div
      style={{
        ...posStyle,
        zIndex: 9999,
        background: '#1a1a2e',
        border: '1px solid rgba(217, 28, 210, 0.2)',
        borderRadius: '12px',
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
        backdropFilter: 'blur(8px)',
        padding: '12px',
        width: '300px',
        maxHeight: '400px',
        display: 'flex',
        flexDirection: 'column',
        animation: 'slideUp 0.2s ease',
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Header with close button */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '10px',
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
          {isSwahili ? '🗣️ Salutations Swahili' : '✨ Émojis Africains'}
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
            e.currentTarget.style.background = 'rgba(217, 28, 210, 0.3)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'rgba(255,255,255,0.05)';
          }}
        >
          <X size={16} />
        </button>
      </div>

      {/* Category Tabs — emoji icons */}
      <div
        style={{
          display: 'flex',
          gap: '4px',
          marginBottom: '10px',
          overflowX: 'auto',
          paddingBottom: '4px',
          scrollBehavior: 'smooth',
        }}
      >
        {/* v154: Onglet Coach custom en premier si des emojis existent */}
        {customEmojis.length > 0 && (
          <CategoryTab
            key="coach_custom"
            icon="⭐"
            label="Coach"
            isActive={activeCategory === 'coach_custom'}
            onClick={() => setActiveCategory('coach_custom')}
          />
        )}
        {Object.entries(EMOJI_CATEGORIES).map(([key, category]) => (
          <CategoryTab
            key={key}
            icon={category.icon}
            label={category.label}
            isActive={activeCategory === key}
            onClick={() => setActiveCategory(key)}
          />
        ))}
      </div>

      {/* Content Grid */}
      <div
        style={{
          overflowY: 'auto',
          overflowX: 'hidden',
          maxHeight: '280px',
          padding: '4px',
          ...(isSwahili
            ? { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }
            : { display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '4px' }
          ),
        }}
      >
        {/* v154: Coach custom emojis tab */}
        {isCoachCustom
          ? customEmojis.map((emoji, index) => (
              <button
                key={`coach-${index}`}
                onClick={() => handleSelectEmoji(`[emoji:${emoji.id}]`)}
                style={{
                  border: '1px solid rgba(217, 28, 210, 0.15)',
                  background: 'rgba(217, 28, 210, 0.06)',
                  cursor: 'pointer',
                  padding: '6px',
                  borderRadius: '8px',
                  transition: 'all 0.2s ease',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '48px',
                  height: '48px',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(217, 28, 210, 0.2)';
                  e.currentTarget.style.transform = 'scale(1.1)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(217, 28, 210, 0.06)';
                  e.currentTarget.style.transform = 'scale(1)';
                }}
                title={emoji.name}
              >
                <img src={emoji.image_data} alt={emoji.name} style={{ width: '32px', height: '32px', objectFit: 'contain' }} />
              </button>
            ))
          : isSwahili
            ? currentCategory.emojis.map((phrase, index) => (
                <SwahiliButton
                  key={`swahili-${index}`}
                  phrase={phrase}
                  onSelect={handleSelectEmoji}
                />
              ))
            : currentCategory.emojis.map((emoji, index) => (
                <EmojiButton
                  key={`${activeCategory}-${index}`}
                  emoji={emoji}
                  onSelect={handleSelectEmoji}
                />
              ))
        }
      </div>

      {/* CSS animation */}
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

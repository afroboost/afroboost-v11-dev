// ChatBubbles.js — v99: Design des bulles de chat premium
// Violet Afroboost #D91CD2 pour le coach/IA
// Anthracite #2A2A2A pour les membres/visiteurs
// Photos cliquables avec lightbox

import React, { useState, memo } from 'react';
import { Check, CheckCheck, Clock, Bot, Image as ImageIcon, X, Trash2 } from 'lucide-react';

// === Photo Lightbox ===
const PhotoLightbox = ({ src, alt, onClose }) => (
  <div
    onClick={onClose}
    style={{
      position: 'fixed', inset: 0, zIndex: 99999,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.9)', backdropFilter: 'blur(8px)',
      cursor: 'zoom-out',
    }}
  >
    <button onClick={onClose} style={{
      position: 'absolute', top: '16px', right: '16px',
      background: 'rgba(255,255,255,0.1)', border: 'none',
      borderRadius: '50%', width: '36px', height: '36px',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      cursor: 'pointer', color: '#fff',
    }}>
      <X size={18} />
    </button>
    <img
      src={src}
      alt={alt || 'Photo'}
      style={{
        maxWidth: '90vw', maxHeight: '90vh',
        borderRadius: '8px', objectFit: 'contain',
      }}
    />
  </div>
);

// === Helper: Render text with clickable links ===
const renderTextWithLinks = (text) => {
  if (!text) return null;

  // Regex to match URLs (http://, https://, www.)
  const urlRegex = /(https?:\/\/[^\s]+|www\.[^\s]+)/g;
  const parts = text.split(urlRegex);

  return parts.map((part, index) => {
    if (urlRegex.test(part)) {
      // It's a URL
      const href = part.startsWith('http') ? part : `https://${part}`;
      return (
        <a
          key={index}
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            color: 'rgba(255,255,255,0.85)',
            textDecoration: 'underline',
            cursor: 'pointer',
          }}
        >
          {part}
        </a>
      );
    }
    return <span key={index}>{part}</span>;
  });
};

// === Avatar Component ===
const BubbleAvatar = memo(({ src, name, isCoach, onClick }) => {
  const initial = (name || '?')[0].toUpperCase();

  return (
    <div
      onClick={onClick}
      style={{
        width: '32px', height: '32px', borderRadius: '50%',
        flexShrink: 0, cursor: src ? 'pointer' : 'default',
        border: isCoach ? '2px solid #D91CD2' : '2px solid rgba(255,255,255,0.1)',
        overflow: 'hidden',
        background: isCoach
          ? 'linear-gradient(135deg, #D91CD2, #9333ea)'
          : 'rgba(255,255,255,0.08)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      {src ? (
        <img src={src} alt={name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      ) : (
        <span style={{ color: '#fff', fontSize: '12px', fontWeight: '700' }}>{initial}</span>
      )}
    </div>
  );
});
BubbleAvatar.displayName = 'BubbleAvatar';

// === Timestamp + Status ===
const BubbleStatus = ({ timestamp, status, isCoach }) => {
  const time = timestamp ? new Date(timestamp).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : '';

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '4px',
      marginTop: '4px', justifyContent: isCoach ? 'flex-start' : 'flex-end',
    }}>
      <span style={{ color: 'rgba(255,255,255,0.2)', fontSize: '9px' }}>{time}</span>
      {!isCoach && status && (
        status === 'sent' ? <Check size={10} color="rgba(255,255,255,0.2)" /> :
        status === 'delivered' ? <CheckCheck size={10} color="rgba(255,255,255,0.2)" /> :
        status === 'read' ? <CheckCheck size={10} color="#D91CD2" /> :
        <Clock size={10} color="rgba(255,255,255,0.15)" />
      )}
    </div>
  );
};

// === Coach/AI Bubble (Violet #D91CD2) ===
const CoachBubble = memo(({ message, avatar, name, onAvatarClick, onDelete }) => {
  const [lightbox, setLightbox] = useState(null);
  const [showDelete, setShowDelete] = useState(false);
  const isAi = message.sender === 'ai' || message.type === 'ai';
  const hasImage = message.image || message.media_url;

  return (
    <>
      {lightbox && <PhotoLightbox src={lightbox} onClose={() => setLightbox(null)} />}
      <div
        style={{
          display: 'flex', gap: '8px', alignItems: 'flex-end',
          maxWidth: '85%', alignSelf: 'flex-start',
          position: 'relative',
        }}
        onMouseEnter={() => setShowDelete(true)}
        onMouseLeave={() => setShowDelete(false)}
      >
        {showDelete && onDelete && (
          <button
            onClick={() => onDelete(message.id)}
            style={{
              position: 'absolute', bottom: '0', right: '-24px',
              background: 'none', border: 'none', cursor: 'pointer',
              opacity: 0.5, transition: 'opacity 0.2s',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: '4px',
            }}
            onMouseEnter={(e) => e.target.style.opacity = '0.8'}
            onMouseLeave={(e) => e.target.style.opacity = '0.5'}
          >
            <Trash2 size={14} color="rgba(255,255,255,0.6)" />
          </button>
        )}
        <BubbleAvatar src={avatar} name={name || 'Coach'} isCoach={true} onClick={onAvatarClick} />
        <div>
          {/* Name + AI badge */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '3px' }}>
            <span style={{ color: '#D91CD2', fontSize: '10px', fontWeight: '700' }}>
              {name || 'Afroboost'}
            </span>
            {isAi && (
              <span style={{
                padding: '1px 5px', borderRadius: '6px',
                background: 'rgba(217,28,210,0.12)',
                fontSize: '8px', color: '#D91CD2', fontWeight: '700',
                display: 'flex', alignItems: 'center', gap: '2px',
              }}>
                <Bot size={8} /> IA
              </span>
            )}
          </div>

          {/* Image */}
          {hasImage && (
            <div
              onClick={() => setLightbox(message.image || message.media_url)}
              style={{
                marginBottom: '4px', cursor: 'pointer',
                borderRadius: '14px 14px 14px 4px', overflow: 'hidden',
                maxWidth: '240px',
              }}
            >
              <img
                src={message.image || message.media_url}
                alt="Photo"
                style={{ width: '100%', display: 'block', borderRadius: '14px 14px 14px 4px' }}
              />
            </div>
          )}

          {/* Text bubble */}
          {message.text && (
            <div style={{
              background: '#D91CD2',
              padding: '10px 14px',
              borderRadius: '14px 14px 14px 4px',
              fontSize: '13px', lineHeight: '1.4',
              color: '#fff',
              boxShadow: '0 2px 8px rgba(217,28,210,0.2)',
              wordBreak: 'break-word',
            }}>
              {message.is_deleted ? (
                <span style={{ fontStyle: 'italic', opacity: 0.7 }}>Message supprimé</span>
              ) : (
                renderTextWithLinks(message.text)
              )}
            </div>
          )}

          <BubbleStatus timestamp={message.created_at || message.timestamp} isCoach={true} />
        </div>
      </div>
    </>
  );
});
CoachBubble.displayName = 'CoachBubble';

// === Member/Visitor Bubble (Anthracite #2A2A2A) ===
const MemberBubble = memo(({ message, avatar, name, onAvatarClick, onDelete, isOwnMessage }) => {
  const [lightbox, setLightbox] = useState(null);
  const [showDelete, setShowDelete] = useState(false);
  const hasImage = message.image || message.media_url;

  return (
    <>
      {lightbox && <PhotoLightbox src={lightbox} onClose={() => setLightbox(null)} />}
      <div
        style={{
          display: 'flex', gap: '8px', alignItems: 'flex-end',
          flexDirection: 'row-reverse',
          maxWidth: '85%', alignSelf: 'flex-end',
          position: 'relative',
        }}
        onMouseEnter={() => setShowDelete(true)}
        onMouseLeave={() => setShowDelete(false)}
      >
        {showDelete && onDelete && isOwnMessage && (
          <button
            onClick={() => onDelete(message.id)}
            style={{
              position: 'absolute', bottom: '0', left: '-24px',
              background: 'none', border: 'none', cursor: 'pointer',
              opacity: 0.5, transition: 'opacity 0.2s',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: '4px',
            }}
            onMouseEnter={(e) => e.target.style.opacity = '0.8'}
            onMouseLeave={(e) => e.target.style.opacity = '0.5'}
          >
            <Trash2 size={14} color="rgba(255,255,255,0.6)" />
          </button>
        )}
        <BubbleAvatar src={avatar} name={name || 'Visiteur'} isCoach={false} onClick={onAvatarClick} />
        <div>
          {/* Name */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '3px' }}>
            <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '10px', fontWeight: '600' }}>
              {name || 'Visiteur'}
            </span>
          </div>

          {/* Image */}
          {hasImage && (
            <div
              onClick={() => setLightbox(message.image || message.media_url)}
              style={{
                marginBottom: '4px', cursor: 'pointer',
                borderRadius: '14px 14px 4px 14px', overflow: 'hidden',
                maxWidth: '240px', marginLeft: 'auto',
              }}
            >
              <img
                src={message.image || message.media_url}
                alt="Photo"
                style={{ width: '100%', display: 'block', borderRadius: '14px 14px 4px 14px' }}
              />
            </div>
          )}

          {/* Text bubble */}
          {message.text && (
            <div style={{
              background: '#2A2A2A',
              padding: '10px 14px',
              borderRadius: '14px 14px 4px 14px',
              fontSize: '13px', lineHeight: '1.4',
              color: '#fff',
              boxShadow: '0 1px 4px rgba(0,0,0,0.15)',
              wordBreak: 'break-word',
            }}>
              {message.is_deleted ? (
                <span style={{ fontStyle: 'italic', opacity: 0.7 }}>Message supprimé</span>
              ) : (
                renderTextWithLinks(message.text)
              )}
            </div>
          )}

          <BubbleStatus
            timestamp={message.created_at || message.timestamp}
            status={message.status || 'sent'}
            isCoach={false}
          />
        </div>
      </div>
    </>
  );
});
MemberBubble.displayName = 'MemberBubble';

// === System Message (centered, subtle) ===
const SystemBubble = memo(({ message }) => (
  <div style={{
    textAlign: 'center', padding: '8px 16px', margin: '4px 0',
  }}>
    <span style={{
      padding: '4px 12px', borderRadius: '10px',
      background: 'rgba(255,255,255,0.04)',
      color: 'rgba(255,255,255,0.3)', fontSize: '10px',
      fontWeight: '500',
    }}>
      {message.text}
    </span>
  </div>
));
SystemBubble.displayName = 'SystemBubble';

// === Typing Indicator ===
const TypingIndicator = memo(({ name }) => (
  <div style={{
    display: 'flex', gap: '8px', alignItems: 'center',
    padding: '4px 0',
  }}>
    <div style={{
      width: '24px', height: '24px', borderRadius: '50%',
      background: 'linear-gradient(135deg, #D91CD2, #9333ea)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <Bot size={12} color="#fff" />
    </div>
    <div style={{
      background: 'rgba(217,28,210,0.08)',
      padding: '8px 14px', borderRadius: '14px 14px 14px 4px',
      display: 'flex', gap: '4px', alignItems: 'center',
    }}>
      {[0, 1, 2].map(i => (
        <div key={i} style={{
          width: '6px', height: '6px', borderRadius: '50%',
          background: '#D91CD2', opacity: 0.5,
          animation: `typingDot 1.2s infinite ${i * 0.2}s`,
        }} />
      ))}
    </div>
    <span style={{ color: 'rgba(255,255,255,0.25)', fontSize: '10px' }}>
      {name || 'Afroboost'} écrit...
    </span>
    <style>{`
      @keyframes typingDot {
        0%, 100% { opacity: 0.3; transform: translateY(0); }
        50% { opacity: 1; transform: translateY(-3px); }
      }
    `}</style>
  </div>
));
TypingIndicator.displayName = 'TypingIndicator';

// === Main ChatBubble dispatcher ===
const ChatBubble = memo(({ message, coachAvatar, coachName, memberAvatar, memberName, onAvatarClick, onDelete, currentUserId }) => {
  const isCoach = message.type === 'ai' || message.sender === 'coach' || message.sender === 'ai';
  const isSystem = message.type === 'system' || message.type === 'info';
  const isOwnMessage = currentUserId && message.sender_id === currentUserId;

  if (isSystem) return <SystemBubble message={message} />;

  if (isCoach) {
    return (
      <CoachBubble
        message={message}
        avatar={coachAvatar || '/logo192.png'}
        name={coachName || 'Afroboost'}
        onAvatarClick={() => onAvatarClick?.('coach')}
        onDelete={onDelete}
      />
    );
  }

  return (
    <MemberBubble
      message={message}
      avatar={memberAvatar}
      name={memberName || message.sender_name}
      onAvatarClick={() => onAvatarClick?.('member', message.sender_id)}
      onDelete={onDelete}
      isOwnMessage={isOwnMessage}
    />
  );
});
ChatBubble.displayName = 'ChatBubble';

export { CoachBubble, MemberBubble, SystemBubble, TypingIndicator, PhotoLightbox, BubbleAvatar };
export default ChatBubble;

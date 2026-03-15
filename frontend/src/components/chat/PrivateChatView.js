/**
 * PrivateChatView.js - Fenêtre flottante de messagerie privée (DM)
 * 
 * Extrait de ChatWidget.js pour alléger le fichier principal.
 * Style: Messenger-like, fenêtre flottante positionnée à côté du chat principal.
 * 
 * Fonctionnalités:
 * - Affichage des messages privés
 * - Indicateur de frappe (3 points animés)
 * - Envoi de messages
 * - Fermeture de la fenêtre
 */

import React, { memo } from 'react';
import { renderTextWithLinks } from './ChatBubbles'; // V156.3: Liens cliquables

/**
 * Composant de la fenêtre de chat privé
 * @param {object} activeChat - Conversation active {id, recipientName, participant_1_id, participant_2_id}
 * @param {array} messages - Liste des messages [{text, sender, isMine, createdAt}]
 * @param {string} inputValue - Valeur actuelle de l'input
 * @param {function} setInputValue - Setter pour l'input
 * @param {function} onSend - Handler d'envoi de message
 * @param {function} onClose - Handler de fermeture
 * @param {function} onInputChange - Handler de changement d'input (pour typing indicator)
 * @param {function} onInputBlur - Handler de blur (arrêter typing)
 * @param {object} typingUser - Utilisateur en train d'écrire {name} ou null
 * @param {boolean} isMainChatOpen - Si le chat principal est ouvert (pour le positionnement)
 */
const PrivateChatView = ({
  activeChat,
  messages,
  inputValue,
  setInputValue,
  onSend,
  onClose,
  onInputChange,
  onInputBlur,
  typingUser,
  isMainChatOpen = true
}) => {
  if (!activeChat) return null;

  return (
    <div
      style={{
        position: 'fixed',
        bottom: '100px',
        right: isMainChatOpen ? '420px' : '20px',
        width: '320px',
        height: '400px',
        borderRadius: '12px',
        background: '#1a1a1a',
        border: '1px solid rgba(147, 51, 234, 0.5)',
        boxShadow: '0 10px 40px rgba(0,0,0,0.5)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        zIndex: 60
      }}
      data-testid="private-chat-window"
    >
      {/* Header */}
      <div style={{
        background: 'linear-gradient(135deg, #9333ea, #7c3aed)',
        padding: '12px 16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div>
          <div style={{ color: '#fff', fontWeight: 'bold', fontSize: '14px' }}>
            💬 {activeChat.recipientName}
          </div>
          <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: '11px' }}>
            Message privé
          </div>
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'rgba(255,255,255,0.2)',
            border: 'none',
            borderRadius: '50%',
            width: '28px',
            height: '28px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontSize: '16px'
          }}
          data-testid="close-private-chat"
        >
          ✕
        </button>
      </div>

      {/* Messages */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '12px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px'
      }}>
        {messages.length === 0 ? (
          <div style={{ color: 'rgba(255,255,255,0.5)', textAlign: 'center', marginTop: '50px' }}>
            Commencez la conversation...
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div
              key={idx}
              style={{
                alignSelf: msg.isMine ? 'flex-end' : 'flex-start',
                maxWidth: '80%'
              }}
            >
              {!msg.isMine && (
                <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.5)', marginBottom: '2px' }}>
                  {msg.sender}
                </div>
              )}
              <div style={{
                background: msg.isMine ? '#9333ea' : '#2d2d2d',
                color: '#fff',
                padding: '8px 12px',
                borderRadius: msg.isMine ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                fontSize: '13px'
              }}>
                {renderTextWithLinks(msg.text)}
              </div>
            </div>
          ))
        )}
        
        {/* Indicateur de frappe DM (3 points animés) */}
        {typingUser && (
          <div 
            style={{ 
              alignSelf: 'flex-start', 
              display: 'flex', 
              alignItems: 'center', 
              gap: '6px',
              padding: '4px 0'
            }}
            data-testid="dm-typing-indicator"
          >
            <div style={{
              display: 'flex',
              gap: '3px',
              padding: '8px 12px',
              background: 'rgba(255,255,255,0.05)',
              borderRadius: '16px'
            }}>
              <span style={{ 
                width: '6px', 
                height: '6px', 
                borderRadius: '50%', 
                background: 'rgba(255,255,255,0.4)',
                animation: 'dmTypingDot 1.4s infinite ease-in-out',
                animationDelay: '0s'
              }}></span>
              <span style={{ 
                width: '6px', 
                height: '6px', 
                borderRadius: '50%', 
                background: 'rgba(255,255,255,0.4)',
                animation: 'dmTypingDot 1.4s infinite ease-in-out',
                animationDelay: '0.2s'
              }}></span>
              <span style={{ 
                width: '6px', 
                height: '6px', 
                borderRadius: '50%', 
                background: 'rgba(255,255,255,0.4)',
                animation: 'dmTypingDot 1.4s infinite ease-in-out',
                animationDelay: '0.4s'
              }}></span>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div style={{
        padding: '12px',
        borderTop: '1px solid rgba(255,255,255,0.1)',
        display: 'flex',
        gap: '8px'
      }}>
        <input
          type="text"
          value={inputValue}
          onChange={(e) => {
            setInputValue(e.target.value);
            if (e.target.value.length > 0 && onInputChange) {
              onInputChange(true);
            }
          }}
          onKeyPress={(e) => {
            if (e.key === 'Enter') {
              if (onInputChange) onInputChange(false);
              onSend();
            }
          }}
          onBlur={() => {
            if (onInputBlur) onInputBlur();
          }}
          placeholder="Message privé..."
          style={{
            flex: 1,
            background: 'rgba(255,255,255,0.1)',
            border: '1px solid rgba(255,255,255,0.2)',
            borderRadius: '20px',
            padding: '8px 16px',
            color: '#fff',
            fontSize: '13px'
          }}
          data-testid="private-message-input"
        />
        <button
          onClick={() => {
            if (onInputChange) onInputChange(false);
            onSend();
          }}
          disabled={!inputValue.trim()}
          style={{
            width: '36px',
            height: '36px',
            borderRadius: '50%',
            background: inputValue.trim() ? '#9333ea' : '#444',
            border: 'none',
            cursor: inputValue.trim() ? 'pointer' : 'not-allowed',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff'
          }}
          data-testid="send-private-btn"
        >
          →
        </button>
      </div>
    </div>
  );
};

export default memo(PrivateChatView);

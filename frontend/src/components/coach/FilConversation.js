/**
 * V619 — LE FIL COMPLET D'UNE CONVERSATION PARTENAIRE.
 *
 * Il AFFICHE `conversation.messages_fil`, une projection calculée par le serveur
 * (`v619_fil`, api/server.py) à partir des collections existantes. L'écran ne
 * reconstruit rien :
 *  - réponse manuelle = `approved_text` (le texte réellement parti), jamais le brouillon ;
 *  - message reçu = `body_text` tel que séparé par le serveur, SANS seconde découpe ;
 *    l'historique cité (`quoted`) reste à part, replié ;
 *  - J0 / relances = texte prouvé par le serveur, sinon « Texte historique non garanti ».
 *
 * Le fil de messages et le journal technique (« Voir l'historique ») sont deux choses
 * différentes : ce composant ne remplace pas le journal.
 */
import React, { useState } from 'react';
import { jourHeure } from '../../utils/prospectionFocus';

const PRIMAIRE_LISIBLE = 'color-mix(in srgb, var(--primary-color, #D91CD2) 80%, white)';
const RGB = 'var(--primary-rgb, 217, 28, 210)';
const TEXTE = '#fff';
const DOUX = 'rgba(255,255,255,0.68)';
/* Couleurs d'ÉTAT (sémantiques, identiques à « Messages & relances »), jamais de marque. */
const VERT = 'rgb(134,239,172)';
const ROUGE = 'rgb(252,165,165)';

/* Au-delà, le message est replié sur quelques lignes : « Voir plus » rend le texte intégral. */
export const LIGNES_REPLIEES = 5;
const CARACTERES_REPLIES = 360;

export const LIBELLES_TYPE = {
  j0: 'Message J0',
  j3: 'Relance J+3',
  j7: 'Relance J+7',
  j14: 'Relance J+14',
  manual_reply: 'Réponse manuelle',
  partner_reply: 'Réponse du partenaire',
};

export const LIBELLES_REMISE = {
  remis: 'Remis',
  en_attente: 'En attente',
  echec: 'Échec',
  rebond: 'Rebond',
  inconnu: 'Remise non suivie',
};

/** Un texte est-il assez long pour être replié ? PURE. */
export function estLong(texte) {
  const t = String(texte || '');
  return t.length > CARACTERES_REPLIES || t.split('\n').length > LIGNES_REPLIEES;
}

function IconeRemise({ remise }) {
  if (remise === 'remis') {
    return (
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
           style={{ marginLeft: '3px', flex: '0 0 auto' }}>
        <polyline points="20 6 9 17 4 12" />
      </svg>
    );
  }
  if (remise === 'echec' || remise === 'rebond') {
    return (
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           strokeWidth="3" strokeLinecap="round" aria-hidden="true"
           style={{ marginLeft: '3px', flex: '0 0 auto' }}>
        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    );
  }
  return null;
}

const styleLien = {
  background: 'transparent', border: 'none', padding: '2px 0', cursor: 'pointer',
  color: PRIMAIRE_LISIBLE, fontSize: '11.5px', fontWeight: 600,
};

export function ElementFil({ e }) {
  const [ouvert, setOuvert] = useState(false);
  const sortant = e.direction === 'outgoing';
  const long = estLong(e.text);
  const couleurRemise = e.remise === 'remis' ? VERT
    : (e.remise === 'echec' || e.remise === 'rebond') ? ROUGE : DOUX;
  return (
    <div data-testid="fil-message" data-direction={e.direction} data-type={e.type}
         style={{ display: 'flex', justifyContent: sortant ? 'flex-end' : 'flex-start' }}>
      <div style={{ width: '100%', maxWidth: '92%', minWidth: 0, boxSizing: 'border-box',
                    padding: '8px 10px', borderRadius: sortant ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
                    background: sortant ? `rgba(${RGB}, 0.18)` : 'rgba(255,255,255,0.08)',
                    border: `1px solid ${sortant ? `rgba(${RGB}, 0.5)` : 'rgba(255,255,255,0.18)'}` }}>
        <div data-testid="fil-entete"
             style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 6px', alignItems: 'baseline',
                      fontSize: '10.5px', color: DOUX }}>
          <span>{jourHeure(e.date) || '—'}</span>
          <span>·</span>
          <strong style={{ letterSpacing: '0.05em', color: sortant ? PRIMAIRE_LISIBLE : TEXTE }}>
            {sortant ? 'ENVOYÉ' : 'REÇU'}
          </strong>
          {sortant && e.remise ? (
            <>
              <span>·</span>
              <span data-testid="fil-remise" data-remise={e.remise}
                    style={{ color: couleurRemise, fontWeight: 600, whiteSpace: 'nowrap',
                             display: 'inline-flex', alignItems: 'center' }}>
                {LIBELLES_REMISE[e.remise] || e.remise}<IconeRemise remise={e.remise} />
              </span>
            </>
          ) : null}
        </div>
        <div data-testid="fil-type" style={{ fontSize: '11px', fontWeight: 700, color: TEXTE, marginTop: '2px' }}>
          {LIBELLES_TYPE[e.type] || e.type}
        </div>
        {e.subject ? (
          <div data-testid="fil-objet" style={{ fontSize: '11px', color: DOUX, marginTop: '2px', overflowWrap: 'anywhere' }}>
            {e.subject}
          </div>
        ) : null}
        {/* Du TEXTE, jamais du HTML. Le texte intégral reste dans la page : replier n'est que visuel. */}
        {typeof e.text === 'string' && e.text.trim() ? (
          <>
            <div data-testid="fil-texte"
                 style={{ fontSize: '12.5px', lineHeight: 1.5, color: TEXTE, whiteSpace: 'pre-wrap',
                          overflowWrap: 'anywhere', marginTop: '5px',
                          ...(long && !ouvert ? { display: '-webkit-box', WebkitLineClamp: LIGNES_REPLIEES,
                                                  WebkitBoxOrient: 'vertical', overflow: 'hidden' } : {}) }}>
              {e.text}
            </div>
            {long ? (
              <button type="button" data-testid="fil-voir-plus" onClick={() => setOuvert(!ouvert)} style={styleLien}>
                {ouvert ? 'Voir moins' : 'Voir plus'}
              </button>
            ) : null}
          </>
        ) : (
          <div data-testid="fil-sans-texte" style={{ fontSize: '11.5px', fontStyle: 'italic', color: DOUX, marginTop: '5px' }}>
            {e.texte_garanti === false
              ? 'Texte historique non garanti'
              : (sortant ? 'Texte non conservé au moment de l’envoi' : '(aucun contenu lisible pour ce message)')}
          </div>
        )}
        {e.quoted ? (
          <details data-testid="fil-cite" style={{ marginTop: '5px' }}>
            <summary style={{ fontSize: '11px', cursor: 'pointer', color: DOUX }}>Voir le message cité</summary>
            <div style={{ fontSize: '11px', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', color: DOUX, marginTop: '4px' }}>
              {e.quoted}
            </div>
          </details>
        ) : null}
      </div>
    </div>
  );
}

export default function FilConversation({ fil }) {
  const elements = Array.isArray(fil) ? fil.filter(Boolean) : [];
  if (!elements.length) return null;
  return (
    <div data-testid="fil-conversation" style={{ display: 'flex', flexDirection: 'column', gap: '7px' }}>
      {elements.map((e, i) => <ElementFil key={e.id || `fil-${i}`} e={e} />)}
    </div>
  );
}

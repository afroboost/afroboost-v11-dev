// V643 — CampagnesDashboard : hub de navigation par cartes.
//
// PRINCIPE : remplace la rangée d'onglets plate (V616) par 3 cartes
// qui servent à la fois de navigation ET d'affichage des métriques.
// Aucun titre de section supplémentaire, aucune rangée KPI séparée.
// Toute la donnée est intégrée dans chaque carte.
//
// data-testid préservés :
//   campagnes-dashboard       (root)
//   campagnes-mode            (role="tablist")
//   campagnes-mode-{id}       (chaque carte-onglet)
//
// Props :
//   campagnesMode        string    'clients' | 'prospection' | 'invitation'
//   setCampagnesMode     fn
//   setShowPartenaires   fn
//   p3Voir               number    prospects à traiter
//   p3Cockpit            object    { total, nbConversations, … }
//   campaigns            array
//   children             ReactNode contenu de la section active

import React from 'react';
import SvgIcon from '../SvgIcon';

const SECTIONS = [
  { id: 'clients',     label: 'Clients',              icone: 'users'   },
  { id: 'prospection', label: 'Prospection',           icone: 'compass' },
  { id: 'invitation',  label: 'Invitation & Parrainage', icone: 'gift'  },
];

function CarteSection({ id, label, icone, actif, onClick, description, urgent }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={actif}
      data-testid={`campagnes-mode-${id}`}
      onClick={onClick}
      style={{
        flex: '1 1 0',
        minHeight: 72,
        padding: '14px 16px',
        borderRadius: 16,
        border: `1px solid ${actif
          ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.40)'
          : 'rgba(255,255,255,0.08)'}`,
        background: actif
          ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.10)'
          : 'rgba(255,255,255,0.03)',
        cursor: 'pointer',
        textAlign: 'left',
        display: 'flex',
        flexDirection: 'column',
        gap: 5,
        transition: 'background 0.15s, border-color 0.15s',
        minWidth: 0,
      }}
    >
      {/* Ligne supérieure : icône + libellé + badge urgent */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
        <SvgIcon
          name={icone}
          size={14}
          color={actif
            ? 'var(--primary-color, #D91CD2)'
            : 'rgba(255,255,255,0.50)'}
        />
        <span style={{
          fontSize: 13, fontWeight: 600,
          color: actif ? '#fff' : 'rgba(255,255,255,0.75)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {label}
        </span>
        {urgent > 0 && (
          <span style={{
            marginLeft: 'auto', flexShrink: 0,
            fontSize: 11, fontWeight: 700, lineHeight: 1,
            padding: '3px 7px', borderRadius: 99,
            background: 'var(--primary-color, #D91CD2)', color: '#fff',
          }}>
            {urgent}
          </span>
        )}
      </div>

      {/* Ligne inférieure : métriques textuelles */}
      {description && (
        <div style={{
          fontSize: 11,
          color: 'rgba(255,255,255,0.35)',
          lineHeight: 1.3,
          paddingLeft: 21,
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {description}
        </div>
      )}
    </button>
  );
}

export default function CampagnesDashboard({
  campagnesMode,
  setCampagnesMode,
  setShowPartenaires,
  p3Voir,
  p3Cockpit,
  campaigns,
  children,
}) {
  const actives = Array.isArray(campaigns)
    ? campaigns.filter(c => c.status === 'active' || c.status === 'sending').length
    : 0;
  const total = Array.isArray(campaigns) ? campaigns.length : 0;

  // Métriques textuelles pour chaque carte
  const meta = {
    clients: {
      description: total > 0
        ? [
            `${total} campagne${total !== 1 ? 's' : ''}`,
            actives > 0 ? `${actives} active${actives !== 1 ? 's' : ''}` : null,
          ].filter(Boolean).join(' · ')
        : null,
      urgent: 0,
    },
    prospection: {
      description: [
        p3Cockpit?.total != null
          ? `${p3Cockpit.total} prospect${p3Cockpit.total !== 1 ? 's' : ''}`
          : null,
        p3Cockpit?.nbConversations != null
          ? `${p3Cockpit.nbConversations} conv.`
          : null,
      ].filter(Boolean).join(' · ') || null,
      urgent: p3Voir || 0,
    },
    invitation: {
      description: null,
      urgent: 0,
    },
  };

  return (
    <div data-testid="campagnes-dashboard">
      {/* ── Hub de navigation (3 cartes) ─────────────────────────── */}
      <div
        role="tablist"
        aria-label="Type de campagnes"
        data-testid="campagnes-mode"
        style={{
          display: 'flex',
          gap: 8,
          marginBottom: 16,
          overflowX: 'auto',
          scrollbarWidth: 'none',
          WebkitOverflowScrolling: 'touch',
        }}
      >
        {SECTIONS.map(s => (
          <CarteSection
            key={s.id}
            id={s.id}
            label={s.label}
            icone={s.icone}
            actif={campagnesMode === s.id}
            onClick={() => { setCampagnesMode(s.id); setShowPartenaires(false); }}
            description={meta[s.id].description}
            urgent={meta[s.id].urgent}
          />
        ))}
      </div>

      {/* ── Contenu de la section active ─────────────────────────── */}
      {children}
    </div>
  );
}

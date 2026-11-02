// V644 — CampagnesDashboard : layout CRM premium avec sidebar + contenu.
//
// PRINCIPE : interface de type CRM professionnel.
//   Desktop : sidebar compacte à gauche + zone de contenu à droite.
//   Mobile  : navigation horizontale compacte en haut.
//   CSS descendant ciblé (data-testid) pour améliorer le rendu des sections
//   enfants sans modifier leurs composants métier.
//
// data-testid préservés :
//   campagnes-dashboard       (root)
//   campagnes-mode            (role="tablist" / navigation)
//   campagnes-mode-{id}       (chaque item de navigation)
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
  { id: 'clients',     label: 'Clients',                icone: 'users',   iconeCompact: 'users',   desc: 'Campagnes e-mail, WhatsApp et push' },
  { id: 'prospection', label: 'Prospection',             icone: 'target',  iconeCompact: 'target',  desc: 'Partenaires et conversations' },
  { id: 'invitation',  label: 'Invitation & Parrainage', icone: 'gift',    iconeCompact: 'gift',    desc: 'Liens, codes et partage' },
];

function NavItem({ id, label, icone, actif, onClick, compteur, sous }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={actif}
      data-testid={`campagnes-mode-${id}`}
      onClick={onClick}
      style={{
        width: '100%',
        padding: '10px 14px',
        borderRadius: 10,
        border: actif ? '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.25)' : '1px solid transparent',
        cursor: 'pointer',
        textAlign: 'left',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        transition: 'all 0.2s ease',
        background: actif
          ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.12)'
          : 'transparent',
      }}
    >
      <span style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        width: 30, height: 30, borderRadius: 8, flexShrink: 0,
        background: actif
          ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.2)'
          : 'rgba(255,255,255,0.04)',
        transition: 'background 0.2s',
      }}>
        <SvgIcon
          name={icone}
          size={15}
          color={actif
            ? 'var(--primary-color, #D91CD2)'
            : 'rgba(255,255,255,0.4)'}
        />
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 13, fontWeight: actif ? 600 : 500,
          color: actif ? '#fff' : 'rgba(255,255,255,0.7)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {label}
        </div>
        {sous && (
          <div style={{
            fontSize: 11, color: 'rgba(255,255,255,0.3)',
            marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {sous}
          </div>
        )}
      </div>
      {compteur > 0 && (
        <span style={{
          flexShrink: 0, fontSize: 10, fontWeight: 700, lineHeight: 1,
          padding: '3px 7px', borderRadius: 99, minWidth: 20, textAlign: 'center',
          background: 'var(--primary-color, #D91CD2)', color: '#fff',
        }}>
          {compteur}
        </span>
      )}
    </button>
  );
}

function NavItemMobile({ id, label, icone, actif, onClick, compteur }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={actif}
      data-testid={`campagnes-mode-${id}`}
      onClick={onClick}
      style={{
        flex: '1 1 0',
        minWidth: 0,
        padding: '10px 6px 8px',
        borderRadius: 0,
        border: 'none',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 3,
        transition: 'color 0.15s',
        background: 'transparent',
        position: 'relative',
      }}
    >
      {actif && <span style={{
        position: 'absolute', top: 0, left: '20%', right: '20%', height: 2,
        borderRadius: '0 0 2px 2px',
        background: 'var(--primary-color, #D91CD2)',
      }} />}
      <span style={{ position: 'relative' }}>
        <SvgIcon
          name={icone}
          size={18}
          color={actif ? 'var(--primary-color, #D91CD2)' : 'rgba(255,255,255,0.35)'}
        />
        {compteur > 0 && (
          <span style={{
            position: 'absolute', top: -4, right: -8,
            fontSize: 9, fontWeight: 700, lineHeight: 1,
            padding: '2px 5px', borderRadius: 99,
            background: 'var(--primary-color, #D91CD2)', color: '#fff',
          }}>
            {compteur}
          </span>
        )}
      </span>
      <span style={{
        fontSize: 10, fontWeight: actif ? 600 : 500,
        color: actif ? '#fff' : 'rgba(255,255,255,0.45)',
        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        maxWidth: '100%',
      }}>
        {label}
      </span>
    </button>
  );
}

function KpiTile({ icone, valeur, label, accent }) {
  return (
    <div style={{
      flex: '1 1 0', minWidth: 110, padding: '14px 16px', borderRadius: 12,
      background: accent
        ? 'rgba(var(--primary-rgb, 217, 28, 210), 0.08)'
        : 'rgba(255,255,255,0.025)',
      border: accent
        ? '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.15)'
        : '1px solid rgba(255,255,255,0.06)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <SvgIcon name={icone} size={13} color={accent ? 'var(--primary-color, #D91CD2)' : 'rgba(255,255,255,0.3)'} />
        <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', fontWeight: 500 }}>{label}</span>
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color: '#fff', letterSpacing: '-0.02em' }}>
        {valeur != null ? valeur : '—'}
      </div>
    </div>
  );
}

function SectionHeader({ section, p3Cockpit, campaigns, p3Voir }) {
  const s = SECTIONS.find(x => x.id === section);
  if (!s) return null;

  let details = null;
  if (section === 'clients') {
    const total = Array.isArray(campaigns) ? campaigns.length : 0;
    const actives = Array.isArray(campaigns) ? campaigns.filter(c => c.status === 'active' || c.status === 'sending').length : 0;
    details = [
      total > 0 ? `${total} campagne${total !== 1 ? 's' : ''}` : null,
      actives > 0 ? `${actives} active${actives !== 1 ? 's' : ''}` : null,
    ].filter(Boolean).join(' · ');
  } else if (section === 'prospection') {
    details = [
      p3Cockpit?.total != null ? `${p3Cockpit.total} prospect${p3Cockpit.total !== 1 ? 's' : ''}` : null,
      p3Cockpit?.nbConversations != null ? `${p3Cockpit.nbConversations} conversation${p3Cockpit.nbConversations !== 1 ? 's' : ''}` : null,
      p3Voir > 0 ? `${p3Voir} à traiter` : null,
    ].filter(Boolean).join(' · ');
  }

  return (
    <div className="v644-section-header" style={{
      display: 'flex', alignItems: 'center', gap: 10,
      paddingBottom: 14, marginBottom: 16,
      borderBottom: '1px solid rgba(255,255,255,0.06)',
    }}>
      <span style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        width: 34, height: 34, borderRadius: 10, flexShrink: 0,
        background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.12)',
      }}>
        <SvgIcon name={s.icone} size={17} color="var(--primary-color, #D91CD2)" />
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: '#fff', margin: 0, lineHeight: 1.3 }}>
          {s.label}
        </h2>
        <p style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', margin: 0, lineHeight: 1.4 }}>
          {details || s.desc}
        </p>
      </div>
    </div>
  );
}

const CRM_CSS = `
  /* ═══ V644 — LAYOUT CRM ═══════════════════════════════════════════════ */

  /* --- Sidebar / mobile toggle ---------------------------------------- */
  .v644-sidebar { display: flex !important; }
  .v644-mobile-nav { display: none !important; }
  @media (max-width: 768px) {
    .v644-sidebar { display: none !important; }
    .v644-mobile-nav { display: flex !important; }
    .v644-section-header { display: none !important; }
    .v644-kpi-row { display: none !important; }
    /* V644 : espace sous la barre fixe (61 px hauteur + 11 px marge) */
    .v644-content { padding-bottom: 72px !important; }
  }

  /* --- Contenu : retirer les card-gradient redondantes ----
       Les sections enfants sont déjà dans la zone de contenu du sidebar ;
       retirer le wrapper card-gradient évite un double cadrage. */
  .v644-content > .card-gradient {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    border-radius: 0 !important;
  }

  /* --- Prospection : split-pane sur desktop ---
       La zone [data-testid="reponses-recues"] contient :
       1. les compteurs (en haut)
       2. les filtres
       3. la file-conversations (liste compacte)
       4. le détail de la conversation (FilConversation)
       On la passe en grid 2 colonnes sur desktop. */
  @media (min-width: 900px) {
    [data-testid="reponses-recues"] {
      display: grid !important;
      grid-template-columns: 320px 1fr !important;
      grid-template-rows: auto 1fr !important;
      gap: 0 16px !important;
      min-height: 500px !important;
      padding: 0 !important;
      border: none !important;
      background: transparent !important;
    }
    /* Compteurs + filtres : pleine largeur au-dessus du split */
    [data-testid="reponses-recues"] > div:first-child,
    [data-testid="reponses-recues"] > [data-testid^="filtres-"],
    [data-testid="reponses-recues"] > div:has([data-testid^="filtre-"]) {
      grid-column: 1 / -1;
    }
    /* La file de conversations : colonne gauche, scroll interne */
    [data-testid="file-conversations"] {
      grid-column: 1;
      max-height: calc(100vh - 340px) !important;
      overflow-y: auto !important;
      padding-right: 8px !important;
      border-right: 1px solid rgba(255,255,255,0.06);
    }
    /* Le détail (tout ce qui suit la file) : colonne droite */
    [data-testid="file-conversations"] ~ div,
    [data-testid="file-conversations"] ~ [data-testid^="conversation-detail"],
    [data-testid="reponses-recues"] > div:last-child:not([data-testid="file-conversations"]) {
      grid-column: 2;
      grid-row: 2;
      overflow-y: auto;
      max-height: calc(100vh - 340px);
    }
  }

  /* --- Conversations : lignes plus compactes sur desktop --- */
  @media (min-width: 769px) {
    [data-testid="conversation-ligne"] {
      padding: 6px 10px !important;
    }
  }

  /* --- MesInvitations : vignettes déjà compactées dans le composant (V644) --- */

  /* --- CampaignManager (Clients) : tableau plus compact --- */
  @media (min-width: 769px) {
    [data-testid="campagnes-modules"] {
      gap: 6px !important;
      margin-bottom: 8px !important;
    }
    [data-testid="campagnes-modules"] > button {
      padding: 8px 10px !important;
      min-height: 36px !important;
      font-size: 12px !important;
    }
    /* Cellules du tableau campagnes */
    .v644-content table td,
    .v644-content table th {
      padding: 6px 8px !important;
      font-size: 12px !important;
    }
    /* En-têtes du tableau */
    .v644-content table thead th {
      font-size: 11px !important;
      padding: 6px 8px !important;
    }
  }

  /* --- Scrollbar discrète dans la zone de contenu --- */
  .v644-content::-webkit-scrollbar { width: 4px; }
  .v644-content::-webkit-scrollbar-track { background: transparent; }
  .v644-content::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }
  .v644-content { scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; }
`;

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

  const meta = {
    clients: {
      sous: total > 0
        ? [
            `${total} campagne${total !== 1 ? 's' : ''}`,
            actives > 0 ? `${actives} active${actives !== 1 ? 's' : ''}` : null,
          ].filter(Boolean).join(' · ')
        : null,
      compteur: actives,
    },
    prospection: {
      sous: [
        p3Cockpit?.total != null ? `${p3Cockpit.total} prospect${p3Cockpit.total !== 1 ? 's' : ''}` : null,
        p3Cockpit?.nbConversations != null ? `${p3Cockpit.nbConversations} conv.` : null,
      ].filter(Boolean).join(' · ') || null,
      compteur: p3Voir || 0,
    },
    invitation: { sous: null, compteur: 0 },
  };

  const handleClick = (id) => {
    setCampagnesMode(id);
    setShowPartenaires(false);
  };

  const kpis = campagnesMode === 'prospection' ? [
    { icone: 'target', valeur: p3Cockpit?.total, label: 'Prospects', accent: true },
    { icone: 'messageCircle', valeur: p3Cockpit?.nbConversations, label: 'Conversations' },
    { icone: 'clock', valeur: p3Voir || null, label: 'À traiter', accent: p3Voir > 0 },
  ] : campagnesMode === 'invitation' ? [
    { icone: 'gift', valeur: null, label: 'Invitations', accent: true },
    { icone: 'link', valeur: null, label: 'Liens actifs' },
    { icone: 'users', valeur: null, label: 'Parrainés' },
  ] : [
    { icone: 'megaphone', valeur: total || null, label: 'Campagnes', accent: true },
    { icone: 'zap', valeur: actives || null, label: 'Actives', accent: actives > 0 },
    { icone: 'target', valeur: p3Cockpit?.total, label: 'Prospects' },
    { icone: 'clock', valeur: p3Voir || null, label: 'À traiter' },
  ];

  return (
    <div data-testid="campagnes-dashboard">
      <style>{CRM_CSS}</style>

      {/* ═══ DESKTOP : sidebar + contenu ═══════════════════════════ */}
      <div style={{
        display: 'flex', gap: 0, minHeight: 'calc(100vh - 220px)',
      }}>
        {/* ── Sidebar ──────────────────────────────────────────────── */}
        <aside className="v644-sidebar" style={{
          width: 220, flexShrink: 0,
          borderRight: '1px solid rgba(255,255,255,0.06)',
          display: 'flex', flexDirection: 'column',
          background: 'rgba(0,0,0,0.15)',
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '16px 14px 12px',
          }}>
            <span style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 28, height: 28, borderRadius: 8,
              background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.15)',
            }}>
              <SvgIcon name="megaphone" size={14} color="var(--primary-color, #D91CD2)" />
            </span>
            <span style={{ fontSize: 14, fontWeight: 700, color: '#fff', letterSpacing: '-0.01em' }}>Campagnes</span>
          </div>

          <div style={{ padding: '0 6px', marginBottom: 8 }}>
            <div style={{
              height: 1, background: 'rgba(255,255,255,0.06)',
            }} />
          </div>

          <nav role="tablist" aria-label="Type de campagnes" data-testid="campagnes-mode"
            style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '0 6px' }}>
            {SECTIONS.map(s => (
              <NavItem
                key={s.id}
                id={s.id}
                label={s.label}
                icone={s.icone}
                actif={campagnesMode === s.id}
                onClick={() => handleClick(s.id)}
                compteur={meta[s.id].compteur}
                sous={meta[s.id].sous}
              />
            ))}
          </nav>

          {/* KPI compacts en bas de sidebar */}
          <div style={{
            marginTop: 'auto', padding: '12px 8px',
            borderTop: '1px solid rgba(255,255,255,0.06)',
          }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: 'rgba(255,255,255,0.25)',
                          textTransform: 'uppercase', letterSpacing: '0.05em',
                          padding: '0 12px 8px' }}>
              Vue d'ensemble
            </div>
            {[
              { icone: 'megaphone', valeur: total, label: 'Campagnes' },
              { icone: 'target', valeur: p3Cockpit?.total, label: 'Prospects' },
              { icone: 'messageCircle', valeur: p3Cockpit?.nbConversations, label: 'Conversations' },
              { icone: 'clock', valeur: p3Voir || null, label: 'À traiter' },
            ].map((k, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '3px 12px',
              }}>
                <SvgIcon name={k.icone} size={12} color="rgba(255,255,255,0.25)" />
                <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', flex: 1 }}>{k.label}</span>
                <span style={{ fontSize: 12, fontWeight: 600,
                               color: k.valeur ? '#fff' : 'rgba(255,255,255,0.2)',
                               fontVariantNumeric: 'tabular-nums' }}>
                  {k.valeur != null ? k.valeur : '—'}
                </span>
              </div>
            ))}
          </div>
        </aside>

        {/* ── Zone de contenu principale ────────────────────────────── */}
        <div className="v644-content" style={{
          flex: 1, minWidth: 0, padding: '0 0 0 20px',
          overflowY: 'auto',
        }}>
          {/* En-tête de section */}
          <SectionHeader section={campagnesMode} p3Cockpit={p3Cockpit} campaigns={campaigns} p3Voir={p3Voir} />

          {/* KPI row contextuel */}
          <div className="v644-kpi-row" style={{
            display: 'flex', gap: 10, marginBottom: 18, overflowX: 'auto',
            scrollbarWidth: 'none',
          }}>
            {kpis.map((k, i) => <KpiTile key={i} {...k} />)}
          </div>

          {/* Contenu de la section */}
          {children}
        </div>
      </div>

      {/* ═══ MOBILE : navigation fixe en bas ═══════════════════════ */}
      <div className="v644-mobile-nav" role="tablist" aria-label="Type de campagnes"
        data-testid="campagnes-mode"
        style={{
          position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 40,
          display: 'flex', padding: '0',
          background: 'rgba(10,10,10,0.97)', backdropFilter: 'blur(12px)',
          borderTop: '1px solid rgba(255,255,255,0.08)',
        }}
      >
        {SECTIONS.map(s => (
          <NavItemMobile
            key={s.id}
            id={s.id}
            label={s.label.replace(' & Parrainage', '')}
            icone={s.iconeCompact}
            actif={campagnesMode === s.id}
            onClick={() => handleClick(s.id)}
            compteur={meta[s.id].compteur}
          />
        ))}
      </div>
    </div>
  );
}

/**
 * V595 — briques visuelles communes aux écrans Vue d'ensemble / Médias / Liens / Résultats.
 * Mêmes tons que « Messages & relances » (V588). La couleur de marque reste celle du coach.
 */
import React from 'react';

export const PRIMAIRE = 'var(--primary-color, #D91CD2)';
export const RGB = 'var(--primary-rgb, 217, 28, 210)';
export const PRIMAIRE_LISIBLE = 'color-mix(in srgb, var(--primary-color, #D91CD2) 80%, white)';
export const TEXTE = '#fff';
export const DOUX = 'rgba(255,255,255,0.65)';
export const BORD = 'rgba(255,255,255,0.12)';
export const AMBRE = 'rgb(252,211,77)';
export const VERT = 'rgb(134,239,172)';
export const ROUGE = 'rgb(252,165,165)';
export const BLEU = 'rgb(147,197,253)';

export const TONS = {
  vert: { fond: 'rgba(34,197,94,0.18)', bord: 'rgba(34,197,94,0.45)', texte: VERT },
  ambre: { fond: 'rgba(245,158,11,0.16)', bord: 'rgba(245,158,11,0.5)', texte: AMBRE },
  rouge: { fond: 'rgba(239,68,68,0.16)', bord: 'rgba(239,68,68,0.45)', texte: ROUGE },
  bleu: { fond: 'rgba(59,130,246,0.16)', bord: 'rgba(96,165,250,0.55)', texte: BLEU },
  neutre: { fond: 'rgba(255,255,255,0.06)', bord: 'rgba(255,255,255,0.22)', texte: 'rgba(255,255,255,0.8)' },
  marque: { fond: `rgba(${RGB}, 0.14)`, bord: `rgba(${RGB}, 0.45)`, texte: PRIMAIRE_LISIBLE },
};

export function Pastille({ ton, children, testid }) {
  const t = TONS[ton] || TONS.neutre;
  return (
    <span data-testid={testid} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '2px 8px',
      borderRadius: '999px', fontSize: '11px', fontWeight: 700, whiteSpace: 'nowrap',
      background: t.fond, border: `1px solid ${t.bord}`, color: t.texte }}>
      {children}
    </span>
  );
}

export function Titre({ children, droite }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px',
      flexWrap: 'wrap', margin: '18px 0 8px' }}>
      <h3 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: TEXTE, letterSpacing: '0.02em' }}>{children}</h3>
      {droite}
    </div>
  );
}

export function Grille({ children, min = 132, testid }) {
  return (
    <div data-testid={testid} style={{ display: 'grid', gap: '8px',
      gridTemplateColumns: `repeat(auto-fill, minmax(min(${min}px, 100%), 1fr))` }}>
      {children}
    </div>
  );
}

export function Carte({ libelle, valeur, aide, ton, testid }) {
  const t = ton ? TONS[ton] : null;
  return (
    <div data-testid={testid} style={{ padding: '10px 12px', borderRadius: '12px', minWidth: 0,
      border: `1px solid ${t ? t.bord : 'rgba(255,255,255,0.10)'}`, background: t ? t.fond : 'rgba(255,255,255,0.04)' }}>
      <div style={{ fontSize: '11px', color: DOUX, lineHeight: 1.25, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{libelle}</div>
      <div style={{ fontSize: '22px', fontWeight: 800, color: t ? t.texte : TEXTE, marginTop: '2px' }}>{valeur}</div>
      {aide && <div style={{ fontSize: '11px', color: DOUX, marginTop: '2px' }}>{aide}</div>}
    </div>
  );
}

export function Puce({ actif, onClick, children, testid }) {
  return (
    <button type="button" onClick={onClick} data-testid={testid} aria-pressed={!!actif}
      style={{ padding: '6px 11px', borderRadius: '999px', fontSize: '12px', cursor: 'pointer', color: TEXTE,
        fontWeight: actif ? 700 : 500,
        border: `1px solid ${actif ? `rgba(${RGB}, 0.7)` : 'rgba(255,255,255,0.14)'}`,
        background: actif ? `rgba(${RGB}, 0.26)` : 'transparent' }}>
      {children}
    </button>
  );
}

export function Bouton({ onClick, children, discret, disabled, testid, type = 'button' }) {
  return (
    <button type={type} onClick={onClick} disabled={disabled} data-testid={testid}
      style={{ padding: '7px 12px', borderRadius: '9px', fontSize: '12px', fontWeight: 600,
        cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.55 : 1,
        display: 'inline-flex', alignItems: 'center', gap: '6px', color: TEXTE,
        border: discret ? `1px solid ${BORD}` : 'none',
        background: discret ? 'transparent' : PRIMAIRE }}>
      {children}
    </button>
  );
}

/** Tableau qui défile DANS sa boîte sur mobile : jamais de défilement horizontal de la page. */
export function Tableau({ colonnes, lignes, testid, vide = 'Aucune donnée' }) {
  return (
    <div data-testid={testid} style={{ overflowX: 'auto', border: `1px solid ${BORD}`, borderRadius: '12px', maxWidth: '100%' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', color: TEXTE, minWidth: '460px' }}>
        <thead>
          <tr>
            {colonnes.map((c, i) => (
              <th key={c.id} style={{ textAlign: i === 0 ? 'left' : 'right', padding: '8px 10px', fontWeight: 600,
                color: DOUX, borderBottom: `1px solid ${BORD}`, whiteSpace: 'nowrap',
                position: i === 0 ? 'sticky' : undefined, left: i === 0 ? 0 : undefined,
                background: i === 0 ? 'rgb(18,12,22)' : undefined }}>{c.libelle}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lignes.length === 0 && (
            <tr><td colSpan={colonnes.length} style={{ padding: '12px', color: DOUX, textAlign: 'center' }}>{vide}</td></tr>
          )}
          {lignes.map((l) => (
            <tr key={l.cle} data-testid={testid ? `${testid}-ligne` : undefined}>
              {colonnes.map((c, i) => (
                <td key={c.id} style={{ textAlign: i === 0 ? 'left' : 'right', padding: '7px 10px',
                  borderBottom: '1px solid rgba(255,255,255,0.06)', whiteSpace: i === 0 ? 'normal' : 'nowrap',
                  fontWeight: i === 0 ? 600 : 400,
                  position: i === 0 ? 'sticky' : undefined, left: i === 0 ? 0 : undefined,
                  background: i === 0 ? 'rgb(18,12,22)' : undefined }}>{c.rendu ? c.rendu(l) : l[c.id]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Bandeau({ ton = 'neutre', children, testid }) {
  const t = TONS[ton] || TONS.neutre;
  return (
    <div data-testid={testid} style={{ padding: '10px 12px', borderRadius: '12px', fontSize: '12px', lineHeight: 1.45,
      background: t.fond, border: `1px solid ${t.bord}`, color: TEXTE }}>
      {children}
    </div>
  );
}

export function EtatLecture({ chargement, erreur, onReessayer }) {
  if (chargement) return <div data-testid="pp-chargement" style={{ color: DOUX, fontSize: '13px', padding: '18px 0' }}>Chargement des données réelles…</div>;
  if (erreur) {
    return (
      <Bandeau ton="rouge" testid="pp-erreur">
        {erreur} {onReessayer && <button type="button" onClick={onReessayer}
          style={{ marginLeft: '6px', background: 'none', border: 'none', color: TEXTE, textDecoration: 'underline', cursor: 'pointer' }}>Réessayer</button>}
      </Bandeau>
    );
  }
  return null;
}

export const champ = {
  width: '100%', boxSizing: 'border-box', padding: '8px 10px', borderRadius: '9px', fontSize: '13px',
  color: TEXTE, background: 'rgba(255,255,255,0.06)', border: `1px solid ${BORD}`, outline: 'none',
};

export function heure(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('fr-CH', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function jour(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('fr-CH', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export function pct(v) { return v === null || v === undefined ? '—' : `${String(v).replace('.', ',')} %`; }
